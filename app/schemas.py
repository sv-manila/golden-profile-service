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
# Reference data: credential databases (registries) & exclusion lists
# --------------------------------------------------------------------------- #
class CredentialDatabaseIn(BaseModel):
    prefix: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    state: Optional[str] = None
    url: Optional[str] = None
    match_status_map: Optional[str] = None
    required_fields: Optional[str] = None


class CredentialDatabaseOut(CredentialDatabaseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ExclusionListIn(BaseModel):
    prefix: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    verify_email: Optional[str] = None


class ExclusionListOut(ExclusionListIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


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
    # Either the numeric FK or the SV-native registry string (resolved/created).
    credential_database_id: Optional[int] = None
    registry_prefix: Optional[str] = None
    match_summary_status: Optional[str] = None
    match_context: Optional[str] = None
    match: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[date] = None
    check_date: Optional[datetime] = None
    resolutions: list[CredentialResolutionIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_registry(self):
        if self.credential_database_id is None and not self.registry_prefix:
            raise ValueError("Either credential_database_id or registry_prefix is required")
        return self


class CredentialMatchSyncResult(BaseModel):
    id: int
    cami_employee_id: int
    credential_database_id: int
    current: bool = True
    superseded_ids: list[int] = Field(default_factory=list)


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
    # Either the numeric FK or the SV-native list prefix (resolved/created).
    exclusion_list_id: Optional[int] = None
    exclusion_list_prefix: Optional[str] = None
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

    @model_validator(mode="after")
    def _require_list(self):
        if self.exclusion_list_id is None and not self.exclusion_list_prefix:
            raise ValueError("Either exclusion_list_id or exclusion_list_prefix is required")
        return self


class ExclusionMatchSyncResult(BaseModel):
    id: int
    cami_employee_id: int
    exclusion_list_id: int
    current: bool = True
    superseded_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Credentialing search
# --------------------------------------------------------------------------- #
class CredentialSearchIn(BaseModel):
    # Registry being checked in CAMI — numeric FK or SV-native registry string.
    credential_database_id: Optional[int] = None
    registry_prefix: Optional[str] = None
    params_credential_id: Optional[str] = None
    params_license_type: Optional[str] = None
    params_first_name: Optional[str] = None
    params_middle_name: Optional[str] = None
    params_last_name: Optional[str] = None
    cami_employee_id: Optional[int] = None

    @model_validator(mode="after")
    def _require_fields(self):
        if self.credential_database_id is None and not self.registry_prefix:
            raise ValueError("Either credential_database_id or registry_prefix is required")
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
    credential_database_id: int
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
    params_certification_state: Optional[str] = None  # registry state, e.g. "NY"
    # Config flags (credential matches only). Expired results are hidden by default.
    include_expired: bool = False       # include matches past their expiry_date
    exclude_no_matches: bool = False    # drop "no match" (NO_MATCH) results

    @model_validator(mode="after")
    def _require_name(self):
        if not (self.params_first_name and self.params_first_name.strip()):
            raise ValueError("params_first_name is required")
        if not (self.params_last_name and self.params_last_name.strip()):
            raise ValueError("params_last_name is required")
        return self


class GeneralCredentialMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cami_employee_id: int
    credential_database_id: int
    registry_prefix: Optional[str] = None
    registry_state: Optional[str] = None
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


class GeneralExclusionMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cami_employee_id: int
    cami_match_id: Optional[int] = None
    exclusion_list_id: int
    exclusion_list_prefix: Optional[str] = None
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
    params_certification_state: Optional[str] = None
    include_expired: bool = False
    exclude_no_matches: bool = False
    # Latest current credential match per registry matching the name (+ filters).
    credential_matches: list[GeneralCredentialMatchOut] = Field(default_factory=list)
    # Current exclusion matches matching the name.
    exclusion_matches: list[GeneralExclusionMatchOut] = Field(default_factory=list)
