"""Checks that every cited source id really exists among the sources given for a slide.

Pure code, no LLM. The slide writer (slide_content_agent.py) runs it on every draft.
"""
from typing import Iterable, List

from app.schemas.slide_content import Bullet


def collect_source_ids(bullets: Iterable[Bullet]) -> List[str]:
    """Every cited id, once each, in the order they are first used."""
    seen: List[str] = []
    for bullet in bullets:
        for source_id in bullet.source_ids:
            if source_id not in seen:
                seen.append(source_id)
    return seen


def find_invalid_source_ids(bullets: Iterable[Bullet], valid_ids: Iterable[str]) -> List[str]:
    """The cited ids that are NOT among valid_ids (the sources supplied for this slide)."""
    valid = set(valid_ids)
    return [source_id for source_id in collect_source_ids(bullets) if source_id not in valid]


def strip_invalid_source_ids(bullets: Iterable[Bullet], valid_ids: Iterable[str]) -> List[Bullet]:
    """New bullets that keep only the valid ids (duplicates inside a bullet are removed too)."""
    valid = set(valid_ids)
    cleaned: List[Bullet] = []
    for bullet in bullets:
        kept: List[str] = []
        for source_id in bullet.source_ids:
            if source_id in valid and source_id not in kept:
                kept.append(source_id)
        cleaned.append(Bullet(text=bullet.text, source_ids=kept))
    return cleaned
