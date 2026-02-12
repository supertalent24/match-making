"""Normalized candidate models - Smart Profiles."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from talent_matching.models.base import Base
from talent_matching.models.enums import SeniorityEnum, VerificationStatusEnum


class NormalizedCandidate(Base):
    """LLM-normalized candidate profile (Smart Profile).

    Contains structured data extracted from raw candidate input.
    """

    __tablename__ = "normalized_candidates"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    raw_candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ═══════════════════════════════════════════════════════════════════
    # IDENTITY & BASIC INFO
    # ═══════════════════════════════════════════════════════════════════
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ═══════════════════════════════════════════════════════════════════
    # LOCATION (normalized)
    # ═══════════════════════════════════════════════════════════════════
    location_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ═══════════════════════════════════════════════════════════════════
    # PROFESSIONAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority_level: Mapped[SeniorityEnum | None] = mapped_column(
        Enum(SeniorityEnum, name="seniority_enum"), nullable=True
    )
    years_of_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ═══════════════════════════════════════════════════════════════════
    # ARRAYS (Multiple Select in Airtable)
    # ═══════════════════════════════════════════════════════════════════
    desired_job_categories: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    skills_summary: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )  # Denormalized for fast filtering
    companies_summary: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )  # Denormalized
    notable_achievements: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    verified_communities: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )

    # ═══════════════════════════════════════════════════════════════════
    # COMPENSATION
    # ═══════════════════════════════════════════════════════════════════
    compensation_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compensation_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compensation_currency: Mapped[str] = mapped_column(String(10), default="USD")

    # ═══════════════════════════════════════════════════════════════════
    # WORK HISTORY METRICS
    # ═══════════════════════════════════════════════════════════════════
    job_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_switches_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_tenure_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    longest_tenure_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ═══════════════════════════════════════════════════════════════════
    # EDUCATION
    # ═══════════════════════════════════════════════════════════════════
    education_highest_degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_field: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_institution: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ═══════════════════════════════════════════════════════════════════
    # ACHIEVEMENTS & RECOGNITION
    # ═══════════════════════════════════════════════════════════════════
    hackathon_wins_count: Mapped[int] = mapped_column(Integer, default=0)
    hackathon_total_prize_usd: Mapped[int] = mapped_column(Integer, default=0)
    solana_hackathon_wins: Mapped[int] = mapped_column(Integer, default=0)

    # ═══════════════════════════════════════════════════════════════════
    # SOCIAL PRESENCE
    # ═══════════════════════════════════════════════════════════════════
    x_handle: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_handle: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_handle: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_followers_total: Mapped[int] = mapped_column(Integer, default=0)

    # ═══════════════════════════════════════════════════════════════════
    # VERIFICATION & REVIEW
    # ═══════════════════════════════════════════════════════════════════
    verification_status: Mapped[VerificationStatusEnum] = mapped_column(
        Enum(VerificationStatusEnum, name="verification_status_enum"),
        default=VerificationStatusEnum.UNVERIFIED,
    )
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ═══════════════════════════════════════════════════════════════════
    # PROCESSING METADATA
    # ═══════════════════════════════════════════════════════════════════
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    skills: Mapped[list["CandidateSkill"]] = relationship(
        "CandidateSkill", back_populates="candidate", cascade="all, delete-orphan"
    )
    experiences: Mapped[list["CandidateExperience"]] = relationship(
        "CandidateExperience", back_populates="candidate", cascade="all, delete-orphan"
    )
    projects: Mapped[list["CandidateProject"]] = relationship(
        "CandidateProject", back_populates="candidate", cascade="all, delete-orphan"
    )
    attributes: Mapped["CandidateAttribute | None"] = relationship(
        "CandidateAttribute", back_populates="candidate", uselist=False
    )
    role_fitness: Mapped[list["CandidateRoleFitness"]] = relationship(
        "CandidateRoleFitness", back_populates="candidate", cascade="all, delete-orphan"
    )
    github_metrics: Mapped["CandidateGithubMetrics | None"] = relationship(
        "CandidateGithubMetrics", back_populates="candidate", uselist=False
    )


class CandidateSkill(Base):
    """Junction table for candidate skills with ratings.

    Maps to Linked Records in Airtable.
    """

    __tablename__ = "candidate_skills"
    __table_args__ = (
        UniqueConstraint("candidate_id", "skill_id", name="uq_candidate_skill"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Foreign keys
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("normalized_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Rating & Experience
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notable_achievement: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    rated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    rating_model: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    candidate: Mapped["NormalizedCandidate"] = relationship(
        "NormalizedCandidate", back_populates="skills"
    )
    skill: Mapped["Skill"] = relationship("Skill")


class CandidateExperience(Base):
    """Work experience entry for a candidate.

    Maps to Linked Records in Airtable.
    """

    __tablename__ = "candidate_experiences"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Foreign key
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("normalized_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Position details
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    position_title: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Skills used in this role (denormalized for context/reference)
    skills_used: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # Ordering
    position_order: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = most recent

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    candidate: Mapped["NormalizedCandidate"] = relationship(
        "NormalizedCandidate", back_populates="experiences"
    )


class CandidateAttribute(Base):
    """Universal soft attributes for a candidate.

    Five scores rated 1-5 by LLM analysis.
    """

    __tablename__ = "candidate_attributes"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_candidate_attributes"),
        CheckConstraint(
            "leadership_score IS NULL OR (leadership_score >= 1 AND leadership_score <= 5)",
            name="ck_leadership_range",
        ),
        CheckConstraint(
            "autonomy_score IS NULL OR (autonomy_score >= 1 AND autonomy_score <= 5)",
            name="ck_autonomy_range",
        ),
        CheckConstraint(
            "technical_depth_score IS NULL OR (technical_depth_score >= 1 AND technical_depth_score <= 5)",
            name="ck_technical_depth_range",
        ),
        CheckConstraint(
            "communication_score IS NULL OR (communication_score >= 1 AND communication_score <= 5)",
            name="ck_communication_range",
        ),
        CheckConstraint(
            "growth_trajectory_score IS NULL OR (growth_trajectory_score >= 1 AND growth_trajectory_score <= 5)",
            name="ck_growth_trajectory_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Foreign key
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("normalized_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Soft scores (1-5)
    leadership_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    autonomy_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_depth_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    communication_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    growth_trajectory_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Reasoning (JSON string for Airtable compatibility)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    rated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    rating_model: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    candidate: Mapped["NormalizedCandidate"] = relationship(
        "NormalizedCandidate", back_populates="attributes"
    )


class CandidateRoleFitness(Base):
    """Fitness score for a candidate's desired role."""

    __tablename__ = "candidate_role_fitness"
    __table_args__ = (
        UniqueConstraint("candidate_id", "role_name", name="uq_candidate_role"),
        CheckConstraint(
            "fitness_score >= 0 AND fitness_score <= 1", name="ck_fitness_range"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Foreign key
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("normalized_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Role fitness
    role_name: Mapped[str] = mapped_column(Text, nullable=False)
    fitness_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string

    # Metadata
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    algorithm_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    candidate: Mapped["NormalizedCandidate"] = relationship(
        "NormalizedCandidate", back_populates="role_fitness"
    )


class CandidateProject(Base):
    """Individual project or hackathon for a candidate.

    Stores projects, hackathons, and side projects separately from work experience.
    This covers both tech and non-tech candidates' portfolio work.
    """

    __tablename__ = "candidate_projects"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Foreign key
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("normalized_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Project details
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    technologies: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # Hackathon-specific fields
    is_hackathon: Mapped[bool] = mapped_column(Boolean, default=False)
    hackathon_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prize_won: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g., "1st Place", "Best DeFi"
    prize_amount_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timeline
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Ordering
    project_order: Mapped[int] = mapped_column(Integer, default=1)  # 1 = most important/recent

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    candidate: Mapped["NormalizedCandidate"] = relationship(
        "NormalizedCandidate", back_populates="projects"
    )


class CandidateGithubMetrics(Base):
    """Basic GitHub metrics for a candidate."""

    __tablename__ = "candidate_github_metrics"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_candidate_github"),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    airtable_record_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Foreign key
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("normalized_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # GitHub profile
    github_username: Mapped[str] = mapped_column(Text, nullable=False)
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metrics
    public_repos: Mapped[int] = mapped_column(Integer, default=0)
    total_stars: Mapped[int] = mapped_column(Integer, default=0)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    languages: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # Metadata
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    candidate: Mapped["NormalizedCandidate"] = relationship(
        "NormalizedCandidate", back_populates="github_metrics"
    )


# Import Skill for type hints
from talent_matching.models.skills import Skill  # noqa: E402
