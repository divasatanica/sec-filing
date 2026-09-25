import tiktoken

from sec_filing_agent.services.chunking_service import build_chunks


def _numeric_fragments(number: str) -> set[str]:
    return {
        number[start:end]
        for start in range(len(number))
        for end in range(start + 3, len(number) + 1)
    }


def test_chunks_respect_token_limit_and_preserve_overlap() -> None:
    content = "\n".join(
        [
            "alpha " * 12,
            "bravo " * 12,
            "charlie " * 12,
            "delta " * 12,
        ]
    )

    chunks = build_chunks(content, max_tokens=30, overlap_tokens=5)
    encoding = tiktoken.get_encoding("cl100k_base")

    assert len(chunks) > 1
    assert all(chunk.token_count <= 30 for chunk in chunks)
    overlap = encoding.decode(encoding.encode(chunks[0].content)[-5:])
    assert chunks[1].content.startswith(overlap)


def test_chunks_split_an_oversized_unpunctuated_line() -> None:
    content = "orbit " * 200

    chunks = build_chunks(content, max_tokens=25, overlap_tokens=5)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 25 for chunk in chunks)
    assert all("orbit" in chunk.content for chunk in chunks)


def test_chunks_do_not_bisect_comma_separated_numbers() -> None:
    number = "$1,234,567.89"
    content = f"{'revenue ' * 8}{number} {'guidance ' * 12}"

    chunks = build_chunks(content, max_tokens=12, overlap_tokens=3)

    assert len(chunks) > 1
    assert any(number in chunk.content for chunk in chunks)
    numeric_fragments = _numeric_fragments(number)
    for chunk in chunks:
        contains_numeric_fragment = any(fragment in chunk.content for fragment in numeric_fragments)
        assert not contains_numeric_fragment or number in chunk.content


def test_chunks_preserve_a_numeric_atom_larger_than_the_configured_budget() -> None:
    number = "1,234,567,890"
    chunks = build_chunks(f"prefix {number} suffix", max_tokens=2, overlap_tokens=1)
    numeric_fragments = _numeric_fragments(number)

    def preserves_number(chunk_content: str) -> bool:
        return number in chunk_content or not any(
            fragment in chunk_content for fragment in numeric_fragments
        )

    assert any(number in chunk.content for chunk in chunks)
    assert all(preserves_number(chunk.content) for chunk in chunks)


def test_chunks_return_no_rows_for_empty_content() -> None:
    assert build_chunks("\n \n") == []
