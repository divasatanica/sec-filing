import tiktoken

from sec_filing_agent.services.chunking_service import build_chunks


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


def test_chunks_return_no_rows_for_empty_content() -> None:
    assert build_chunks("\n \n") == []
