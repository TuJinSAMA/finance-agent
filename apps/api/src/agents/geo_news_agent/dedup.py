from src.models.geo_event import RawGeoArticle


def _tokenize(text: str) -> set[str]:
    return set(text.lower().split())


def jaccard_similarity(a: str, b: str) -> float:
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def deduplicate_articles(
    articles: list[RawGeoArticle],
    threshold: float = 0.7,
) -> list[RawGeoArticle]:
    if not articles:
        return articles

    seen: list[tuple[set[str], RawGeoArticle]] = []

    for article in articles:
        tokens = _tokenize(article.title)
        if not tokens:
            continue

        is_duplicate = False
        for existing_tokens, existing in seen:
            intersection = tokens & existing_tokens
            union = tokens | existing_tokens
            if union and len(intersection) / len(union) >= threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            seen.append((tokens, article))

    return [article for _, article in seen]
