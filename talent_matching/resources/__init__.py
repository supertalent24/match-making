"""Dagster resources for the talent matching pipeline."""

from talent_matching.resources.airtable import AirtableResource
from talent_matching.resources.github import GitHubAPIResource
from talent_matching.resources.linkedin import LinkedInAPIResource
from talent_matching.resources.openrouter import OpenRouterResource
from talent_matching.resources.twitter import TwitterAPIResource

__all__ = [
    "AirtableResource",
    "GitHubAPIResource",
    "TwitterAPIResource",
    "LinkedInAPIResource",
    "OpenRouterResource",
]
