import os


def make_llm():
    from openai import OpenAI
    key, model = os.environ.get("OPENROUTER_API_KEY"), os.environ.get("LLM_MODEL")
    if not key or not model:
        raise SystemExit("請在 .env 填 OPENROUTER_API_KEY 和 LLM_MODEL")
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)

    def chat(prompt):
        r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content or ""
    return chat
