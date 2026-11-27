import pytest

from app.integrations.llm.research import OpenAIResearchClient, parse_response

pytestmark = pytest.mark.anyio

RESPONSE = {
    "output_text": "**Yes.**\n- GST on laptops is 18% [source]",
    "output": [
        {"type": "web_search_call", "action": {"type": "search", "sources": [{"url": "https://cbic.gov.in/a", "title": "CBIC"}]}},
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "**Yes.**\n- GST on laptops is 18% [source]",
                    "annotations": [
                        {"type": "url_citation", "url": "https://gst.gov.in/x", "title": "GST portal", "start_index": 0, "end_index": 5}
                    ],
                }
            ],
        },
    ],
}


def test_parse_response_extracts_text_citations_and_sources():
    text, cites, sources, web = parse_response(RESPONSE)
    assert text.startswith("**Yes.**") and web is True
    assert cites == [{"url": "https://gst.gov.in/x", "title": "GST portal"}]
    assert {s["url"] for s in sources} == {"https://cbic.gov.in/a", "https://gst.gov.in/x"}  # consulted + cited


class FakeResponses:
    def __init__(self, fail_with_tools: bool) -> None:
        self.calls: list[dict] = []
        self.fail_with_tools = fail_with_tools

    async def create(self, **kw):
        self.calls.append(kw)
        if self.fail_with_tools and "tools" in kw:
            raise ValueError("web_search not supported for this model")
        return RESPONSE if "tools" in kw else {"output_text": "- answered offline", "output": []}


class FakeClient:
    def __init__(self, fail: bool) -> None:
        self.responses = FakeResponses(fail)


async def test_ask_sends_web_search_tool_store_data_and_history():
    fake = FakeClient(fail=False)
    c = OpenAIResearchClient("k", "gpt-test", client=fake)
    r = await c.ask("What is GST on laptops?", [{"role": "user", "content": "hi"}], '{"revenue": "1"}', use_web=True)
    call = fake.responses.calls[0]
    assert call["tools"][0]["type"] == "web_search" and call["include"] == ["web_search_call.action.sources"]
    assert call["input"][0] == {"role": "user", "content": "hi"} and "STORE DATA" in call["input"][-1]["content"]
    assert "bullet" in call["instructions"] and r.web_used and r.citations and r.notice is None


async def test_falls_back_without_web_search_and_says_so():
    fake = FakeClient(fail=True)
    r = await OpenAIResearchClient("k", "old-model", client=fake).ask("q", [], None, use_web=True)
    assert len(fake.responses.calls) == 2 and "tools" not in fake.responses.calls[1]
    assert r.text == "- answered offline" and not r.web_used and "Web search unavailable" in (r.notice or "")
