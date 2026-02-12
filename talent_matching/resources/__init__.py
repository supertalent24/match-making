"""Dagster resources for the talent matching pipeline."""

from talent_matching.resources.airtable import AirtableResource
from talent_matching.resources.embeddings import MockEmbeddingResource
from talent_matching.resources.github import GitHubAPIResource
from talent_matching.resources.linkedin import LinkedInAPIResource
from talent_matching.resources.llm import MockLLMResource
from talent_matching.resources.twitter import TwitterAPIResource

__all__ = [
    "AirtableResource",
    "MockLLMResource",
    "MockEmbeddingResource",
    "GitHubAPIResource",
    "TwitterAPIResource",
    "LinkedInAPIResource",
]
