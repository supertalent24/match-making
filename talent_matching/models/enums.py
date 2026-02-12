"""Database enums for the Talent Matching schema."""

import enum


class ProcessingStatusEnum(str, enum.Enum):
    """Status of raw data processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SeniorityEnum(str, enum.Enum):
    """Career seniority levels."""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


class VerificationStatusEnum(str, enum.Enum):
    """Candidate verification status."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    FRAUDULENT = "fraudulent"


class ReviewStatusEnum(str, enum.Enum):
    """Review status for skills and other entities."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CompanyStageEnum(str, enum.Enum):
    """Company growth stage."""

    STARTUP = "startup"
    SCALEUP = "scaleup"
    ENTERPRISE = "enterprise"
    DAO = "dao"


class EmploymentTypeEnum(str, enum.Enum):
    """Type of employment."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"


class LocationTypeEnum(str, enum.Enum):
    """Work location type."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class RequirementTypeEnum(str, enum.Enum):
    """Skill requirement type for jobs."""

    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class JobStatusEnum(str, enum.Enum):
    """Job posting status."""

    ACTIVE = "active"
    PAUSED = "paused"
    FILLED = "filled"
    CLOSED = "closed"


class MatchStatusEnum(str, enum.Enum):
    """Match review status."""

    MATCHED = "matched"
    REVIEWED = "reviewed"
    CONTACTED = "contacted"
    REJECTED = "rejected"
    HIRED = "hired"
