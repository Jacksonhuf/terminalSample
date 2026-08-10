"""Mapping service: preview, apply rules, and sync staged data to ontology."""

from __future__ import annotations

from typing import Any

from ontology_platform.connector.schema import RecordMapping, FieldMapping
from ontology_platform.connector.store import ConnectorStore
from ontology_platform.mapping.schema import FieldRule, MappingProfile, PreviewResult, StagedSummary
from ontology_platform.mapping.store import MappingStore
from ontology_platform.ontology.schema import OntologyObject
from ontology_platform.ontology.service import OntologyService


class MappingService:
    def __init__(
        self,
        mapping_store: MappingStore,
        connector_store: ConnectorStore,
    ) -> None:
        self.mapping_store = mapping_store
        self.connector_store = connector_store

    def list_staging_summary(self, connector_name: str | None = None) -> list[StagedSummary]:
        rows = self.connector_store.summarize_staged(connector_name)
        return [
            StagedSummary(
                connector_name=r["connector_name"],
                record_type=r["record_type"],
                total=r["total"],
                unsynced=r["unsynced"],
                synced=r["synced"],
                sample_fields=self.connector_store.infer_fields(
                    r["connector_name"], r["record_type"]
                ),
            )
            for r in rows
        ]

    def get_sample_payloads(
        self,
        connector_name: str,
        record_type: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        records = self.connector_store.list_staged_records(
            connector_name=connector_name,
            record_type=record_type,
            limit=limit,
        )
        return [r.payload for r in records]

    def profile_to_record_mapping(self, profile: MappingProfile) -> RecordMapping:
        return RecordMapping(
            record_type=profile.record_type,
            object_type=profile.object_type,
            id_field=profile.id_field,
            field_mappings=[
                FieldMapping(source=rule.source, target=rule.target)
                for rule in profile.field_rules
            ],
        )

    def apply_field_rules(self, payload: dict[str, Any], profile: MappingProfile) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for rule in profile.field_rules:
            raw = payload.get(rule.source)
            if raw is None and rule.transform.type != "default":
                continue
            if rule.transform.type == "map":
                mapped = rule.transform.mapping.get(str(raw), rule.transform.default)
                if mapped is not None:
                    result[rule.target] = mapped
            elif rule.transform.type == "default":
                result[rule.target] = rule.transform.default if raw is None else raw
            else:
                result[rule.target] = raw
        if profile.id_field not in result:
            source_id = payload.get(profile.source_id_field)
            if source_id is not None:
                result[profile.id_field] = source_id
        return result

    def preview(
        self,
        profile: MappingProfile,
        *,
        limit: int = 10,
    ) -> list[PreviewResult]:
        records = self.connector_store.list_staged_records(
            connector_name=profile.connector_name,
            record_type=profile.record_type,
            limit=limit,
        )
        results: list[PreviewResult] = []
        for record in records:
            errors: list[str] = []
            try:
                props = self.apply_field_rules(record.payload, profile)
                object_id = str(props.get(profile.id_field, record.external_id))
                if not object_id:
                    errors.append("Missing object id after mapping")
            except Exception as exc:
                props = {}
                object_id = ""
                errors.append(str(exc))
            results.append(
                PreviewResult(
                    source_external_id=record.external_id,
                    mapped_properties=props,
                    object_id=object_id,
                    errors=errors,
                )
            )
        return results

    def sync_profile(
        self,
        profile_id: str,
        ontology_service: OntologyService,
        *,
        resync: bool = False,
        run_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        profile = self.mapping_store.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"Mapping profile not found: {profile_id}")
        if profile.status != "active":
            raise ValueError("Only active mapping profiles can be synced")

        if resync:
            self.connector_store.reset_synced(profile.connector_name, profile.record_type)

        run = self.mapping_store.create_sync_run(profile, resync=resync)
        staged = self.connector_store.list_staged_records(
            connector_name=profile.connector_name,
            record_type=profile.record_type,
            synced=False,
            run_id=run_id,
            limit=limit,
        )

        synced = 0
        failed = 0
        errors: list[str] = []

        for record in staged:
            run.records_processed += 1
            try:
                properties = self.apply_field_rules(record.payload, profile)
                object_id = str(properties.get(profile.id_field, record.external_id))
                if not object_id:
                    raise ValueError("Missing object id after mapping")

                existing = ontology_service.get_object(profile.object_type, object_id)
                if existing:
                    props = dict(existing.properties)
                    props.update(properties)
                    ontology_service.store.update_object(
                        OntologyObject(
                            object_type=profile.object_type,
                            object_id=object_id,
                            properties=props,
                        )
                    )
                else:
                    ontology_service.create_object(
                        profile.object_type, properties, object_id=object_id
                    )
                self.connector_store.mark_synced(record.id, object_id)
                synced += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{record.external_id}: {exc}")

        run.records_synced = synced
        run.records_failed = failed
        run.errors = errors
        run.status = "completed" if not errors else ("failed" if synced == 0 else "completed")
        self.mapping_store.complete_sync_run(run)

        return {
            "run_id": run.id,
            "profile_id": profile_id,
            "synced": synced,
            "failed": failed,
            "errors": errors,
        }
