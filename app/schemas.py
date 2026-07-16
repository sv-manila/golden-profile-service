"""Pydantic request/response models for the API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --------------------------------------------------------------------------- #
# Shared value objects
# --------------------------------------------------------------------------- #
class NameIn(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    maiden_name: Optional[str] = None


class EntityNameIn(BaseModel):
    name: str


class AddressIn(BaseModel):
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class LicensingCredentialIn(BaseModel):
    certification_number: Optional[str] = None
    certification_state: Optional[str] = None
    license_type_id: Optional[str] = None
    license_type: Optional[str] = None
    csl_number: Optional[str] = None
    csl_state: Optional[str] = None
    dea_number: Optional[str] = None
    certification_board: Optional[str] = None


# --------------------------------------------------------------------------- #
# Employee sync
# --------------------------------------------------------------------------- #
class IndividualSyncIn(BaseModel):
    employee_type: Literal["individual"] = "individual"
    cami_employee_id: int
    npi: Optional[int] = None
    facility_id: Optional[str] = None
    terminated: bool = False
    date_of_termination: Optional[datetime] = None
    date_termination_entered: Optional[datetime] = None
    termination_note: Optional[str] = None
    date_of_birth: Optional[date] = None
    date_hire: Optional[date] = None
    job_title: Optional[str] = None
    social_security_num: Optional[str] = None
    ssn_hash: Optional[str] = None
    ssn_last_four: Optional[str] = None
    mmis_number: Optional[str] = None
    record_status: Optional[str] = None
    last_updated_in_cami: Optional[datetime] = None
    names: list[NameIn] = Field(default_factory=list)
    credentials: list[LicensingCredentialIn] = Field(default_factory=list)
    addresses: list[AddressIn] = Field(default_factory=list)


class EntitySyncIn(BaseModel):
    employee_type: Literal["entity"] = "entity"
    cami_employee_id: int
    npi: Optional[int] = None
    facility_id: Optional[str] = None
    terminated: bool = False
    date_of_termination: Optional[datetime] = None
    date_termination_entered: Optional[datetime] = None
    termination_note: Optional[str] = None
    upin: Optional[str] = None
    tin: Optional[str] = None
    tin_hash: Optional[str] = None
    tin_last_four: Optional[str] = None
    mmis_number: Optional[str] = None
    last_updated_in_cami: Optional[datetime] = None
    names: list[EntityNameIn] = Field(default_factory=list)
    addresses: list[AddressIn] = Field(default_factory=list)


class EmployeeSyncResult(BaseModel):
    employee_type: str
    cami_employee_id: int
    id: int
    current: bool = True
    superseded_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Credential match sync
# --------------------------------------------------------------------------- #
class CredentialResolutionIn(BaseModel):
    note: Optional[str] = None


class CredentialMatchSyncIn(BaseModel):
    cami_employee_id: int
    cami_credential_match_id: Optional[int] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    params_credential_id: Optional[str] = None
    params_license_type: Optional[str] = None
    # SV-native registry prefix (e.g. "nursysny"). The client sends this as
    # `registry_prefix`, accepted as an alias below.
    registry: Optional[str] = None
    match_summary_status: Optional[str] = None
    match_context: Optional[str] = None
    match: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[date] = None
    check_date: Optional[datetime] = None
    resolutions: list[CredentialResolutionIn] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_registry_prefix(cls, data):
        # The client sends `registry_prefix`; accept it as `registry`.
        if isinstance(data, dict) and "registry" not in data and "registry_prefix" in data:
            data = {**data, "registry": data["registry_prefix"]}
        return data

    @model_validator(mode="after")
    def _require_registry(self):
        if not (self.registry and self.registry.strip()):
            raise ValueError("registry is required")
        return self


class CredentialMatchSyncResult(BaseModel):
    id: Optional[int] = None            # None when skipped (no row written)
    cami_employee_id: int
    registry: Optional[str] = None
    skipped: bool = False               # true = no-match, dropped, not stored


class CredentialMatchBulkSyncIn(BaseModel):
    """Batch credential-match sync — one HTTP round-trip for a whole Check List."""
    items: list[CredentialMatchSyncIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_items(self):
        if not self.items:
            raise ValueError("items must be a non-empty list")
        return self


class CredentialMatchBulkSyncResult(BaseModel):
    count: int
    results: list[CredentialMatchSyncResult] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Exclusion match sync
# --------------------------------------------------------------------------- #
class ExclusionActionIn(BaseModel):
    action_type: Optional[str] = None
    note: Optional[str] = None
    resolution_source_data: Optional[str] = None
    status: Optional[bool] = None
    is_dob_mismatch: bool = False
    is_ssn_mismatch: bool = False
    is_first_name_mismatch: bool = False
    is_middle_name_mismatch: bool = False
    is_last_name_mismatch: bool = False
    is_address_mismatch: bool = False
    is_npi_mismatch: bool = False
    is_job_mismatch: bool = False
    resolved_via: Optional[str] = None


class ExclusionMatchSyncIn(BaseModel):
    cami_employee_id: int
    cami_match_id: Optional[int] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    # SV-native exclusion-list prefix (e.g. "oig"). The client sends this as
    # `exclusion_list_prefix`, accepted as an alias below.
    prefix: Optional[str] = None
    match: Optional[str] = None
    hash: Optional[str] = Field(default=None, description="Hex-encoded 16-byte hash")
    is_npi_match: bool = False
    is_canonical_name_match: bool = False
    is_diminutive_name_match: bool = False
    is_aka_name_match: bool = False
    is_npi_mismatch: bool = False
    is_upin_match: bool = False
    is_ssn_match: bool = False
    is_license_number_match: bool = False
    date_contacted_agency: Optional[datetime] = None
    check_date: Optional[datetime] = None
    actions: list[ExclusionActionIn] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_list_prefix(cls, data):
        # The client sends `exclusion_list_prefix`; accept it as `prefix`.
        if isinstance(data, dict) and "prefix" not in data and "exclusion_list_prefix" in data:
            data = {**data, "prefix": data["exclusion_list_prefix"]}
        return data

    @model_validator(mode="after")
    def _require_prefix(self):
        if not (self.prefix and self.prefix.strip()):
            raise ValueError("prefix is required")
        return self


class ExclusionMatchSyncResult(BaseModel):
    id: int
    cami_employee_id: int
    prefix: Optional[str] = None


# --------------------------------------------------------------------------- #
# Credentialing search
# --------------------------------------------------------------------------- #
class CredentialSearchIn(BaseModel):
    # Registry being checked in CAMI — SV-native registry string (e.g. "nursysny").
    registry: Optional[str] = None
    params_credential_id: Optional[str] = None
    params_license_type: Optional[str] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    npi: Optional[str] = None  # optional filter: match the `npi` in the result JSON
    cami_employee_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_registry_prefix(cls, data):
        # The client sends `registry_prefix`; accept it as `registry`.
        if isinstance(data, dict) and "registry" not in data and "registry_prefix" in data:
            data = {**data, "registry": data["registry_prefix"]}
        return data

    @model_validator(mode="after")
    def _require_fields(self):
        if not (self.registry and self.registry.strip()):
            raise ValueError("registry is required")
        if not (self.params_first_name and self.params_first_name.strip()):
            raise ValueError("params_first_name is required")
        if not (self.params_last_name and self.params_last_name.strip()):
            raise ValueError("params_last_name is required")
        return self


SearchAction = Literal["return_result", "auto_resolve_name_mismatch", "trigger_scrape"]


class CredentialMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cami_employee_id: int
    cami_credential_match_id: Optional[int] = None
    registry: Optional[str] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    params_credential_id: Optional[str] = None
    params_license_type: Optional[str] = None
    match_summary_status: Optional[str] = None
    match_context: Optional[str] = None
    match: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[date] = None
    check_date: Optional[datetime] = None


class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    credential_match_id: int
    note: Optional[str] = None
    date_created: datetime


class CredentialSearchResult(BaseModel):
    found: bool
    action: SearchAction
    source: str = "golden_profile"
    reason: str
    # Age (days) of the match this decision was based on, when known — lets CAMI
    # log/telemeter cache freshness even on a stale-triggered scrape.
    age_days: Optional[int] = None
    credential_match: Optional[CredentialMatchOut] = None
    resolution: Optional[ResolutionOut] = None


# --------------------------------------------------------------------------- #
# General (name-based) search
# --------------------------------------------------------------------------- #
class GeneralSearchIn(BaseModel):
    # Required.
    params_first_name: str
    params_last_name: str
    # Optional filters applied to the credential matches only.
    params_credential_id: Optional[str] = None       # license number
    npi: Optional[str] = None                          # match the `npi` in the result JSON
    # Config flags (credential matches only). Expired results are hidden by default.
    include_expired: bool = False       # include matches past their expiry_date
    exclude_no_matches: bool = False    # drop "no match" (NO_MATCH) results
    # Entity resolution: expand the name match to the whole canonical person
    # (records linked by shared NPI / license), so differently-spelled records
    # of the same person are included. Off = exact-name records only.
    resolve: bool = True

    @model_validator(mode="after")
    def _require_name(self):
        if not (self.params_first_name and self.params_first_name.strip()):
            raise ValueError("params_first_name is required")
        if not (self.params_last_name and self.params_last_name.strip()):
            raise ValueError("params_last_name is required")
        return self


class GeneralCredentialConflictOut(BaseModel):
    """A recent snapshot for the same (registry, license) whose validity
    determination disagrees with the winning match. Exposed so CAMI can show
    the disagreement rather than silently trusting one answer."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    valid: bool
    match_summary_status: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[date] = None
    check_date: Optional[datetime] = None


class GeneralCredentialMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cami_employee_id: int
    registry: Optional[str] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    params_credential_id: Optional[str] = None
    params_license_type: Optional[str] = None
    match_summary_status: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[date] = None
    check_date: Optional[datetime] = None
    match: Optional[str] = None
    # Conflict signal: the winning match disagrees with one or more recent
    # snapshots for the same registry + license. Empty list => no disagreement.
    has_conflict: bool = False
    conflicts: list[GeneralCredentialConflictOut] = []


# --------------------------------------------------------------------------- #
# Entity resolution
# --------------------------------------------------------------------------- #
class ResolveIn(BaseModel):
    # Strong identifiers (any one anchors a merge). Name is review-only.
    npi: Optional[str] = None
    license_number: Optional[str] = None
    registry: Optional[str] = None          # required alongside license_number
    params_first_name: Optional[str] = None
    params_last_name: Optional[str] = None


class ResolveLicense(BaseModel):
    registry: Optional[str] = None
    number: Optional[str] = None


class ResolveIdentifiers(BaseModel):
    npi: list[str] = []
    licenses: list[ResolveLicense] = []


class ResolveName(BaseModel):
    first: Optional[str] = None
    last: Optional[str] = None


class ResolveOut(BaseModel):
    # True only when a strong identifier produced a canonical group.
    resolved: bool
    # How the group was anchored: "npi" | "license" | "name_only" | "none".
    match_basis: str
    # The unified person: every cami_employee_id linked by shared strong ids.
    canonical_employee_ids: list[int] = []
    # Name-only matches that were NOT merged (need confirmation before merge).
    name_only_candidates: list[int] = []
    identifiers: ResolveIdentifiers = ResolveIdentifiers()
    names: list[ResolveName] = []


class ResolveRebuildResult(BaseModel):
    employees: int
    groups: int


class ResolveSuggestionsIn(BaseModel):
    params_first_name: str
    params_last_name: str


class ResolveSuggestion(BaseModel):
    cami_employee_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    score: float
    reason: str


class ResolveSuggestionsOut(BaseModel):
    params_first_name: str
    params_last_name: str
    # Review-only candidates — the caller confirms; the service never merges these.
    suggestions: list[ResolveSuggestion] = []


class GeneralExclusionMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cami_employee_id: int
    cami_match_id: Optional[int] = None
    prefix: Optional[str] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    match: Optional[str] = None
    is_npi_match: bool = False
    is_ssn_match: bool = False
    is_license_number_match: bool = False
    check_date: Optional[datetime] = None


class GeneralSearchResult(BaseModel):
    params_first_name: str
    params_last_name: str
    params_credential_id: Optional[str] = None
    include_expired: bool = False
    exclude_no_matches: bool = False
    # Every cami_employee_id folded into this person by entity resolution.
    canonical_employee_ids: list[int] = Field(default_factory=list)
    # Latest credential match per registry matching the name (+ filters).
    credential_matches: list[GeneralCredentialMatchOut] = Field(default_factory=list)
    # Latest exclusion matches matching the name.
    exclusion_matches: list[GeneralExclusionMatchOut] = Field(default_factory=list)
