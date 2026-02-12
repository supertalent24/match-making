"""SQLAlchemy models for the Talent Matching database."""

from talent_matching.models.base import Base
from talent_matching.models.enums import (
    CompanyStageEnum,
    EmploymentTypeEnum,
    JobStatusEnum,
    LocationTypeEnum,
    MatchStatusEnum,
    ProcessingStatusEnum,
    RequirementTypeEnum,
    ReviewStatusEnum,
    SeniorityEnum,
    VerificationStatusEnum,
)
from talent_matching.models.raw import RawCandidate, RawJob
from talent_matching.models.skills import Skill, SkillAlias
from talent_matching.models.candidates import (
    NormalizedCandidate,
    CandidateSkill,
    CandidateExperience,
    CandidateProject,
    CandidateAttribute,
    CandidateRoleFitness,
    CandidateGithubMetrics,
    CandidateTwitterMetrics,
    CandidateLinkedinMetrics,
)
from talent_matching.models.jobs import NormalizedJob, JobRequiredSkill
from talent_matching.models.matches import Match
from talent_matching.models.vectors import CandidateVector, JobVector
from talent_matching.models.llm_costs import LLMCost

__all__ = [
    # Base
    "Base",
    # Enums
    "ProcessingStatusEnum",
    "SeniorityEnum",
    "VerificationStatusEnum",
    "ReviewStatusEnum",
    "CompanyStageEnum",
    "EmploymentTypeEnum",
    "LocationTypeEnum",
    "RequirementTypeEnum",
    "JobStatusEnum",
    "MatchStatusEnum",
    # Raw tables
    "RawCandidate",
    "RawJob",
    # Skills
    "Skill",
    "SkillAlias",
    # Candidates
    "NormalizedCandidate",
    "CandidateSkill",
    "CandidateExperience",
    "CandidateProject",
    "CandidateAttribute",
    "CandidateRoleFitness",
    "CandidateGithubMetrics",
    "CandidateTwitterMetrics",
    "CandidateLinkedinMetrics",
    # Jobs
    "NormalizedJob",
    "JobRequiredSkill",
    # Matches
    "Match",
    # Vectors
    "CandidateVector",
    "JobVector",
    # LLM Costs
    "LLMCost",
]
