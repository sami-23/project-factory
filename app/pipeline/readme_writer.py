import anthropic
from app.config import get_settings

CLAUDE_MODEL = "claude-sonnet-4-6"


def write_readme(idea: dict, files: list[tuple[str, str]], stdout: str, github_url: str, log) -> str:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    file_str = "\n\n".join(
        f"**{name}**\n```{idea['language']}\n{code[:1500]}\n```"
        for name, code in files
    )

    prompt = f"""Write a polished, professional README.md for this GitHub project.

Title: {idea['title']}
Language: {idea['language']}  |  Type: {idea['project_type']}
Tech stack: {', '.join(idea['tech_stack'])}
Repo: {github_url}

Description:
{idea['description']}

Code files:
{file_str}

Sample output (what it produced when run):
```
{(stdout or 'See project for output')[:600]}
```

Include these sections in order:
1. Project title with a fitting emoji + one-line tagline
2. Short description (2-3 sentences)
3. Features list with emoji bullets
4. Installation & running — exact shell commands
5. Tech stack table
6. Screenshot: exactly this line → `![Screenshot](screenshot.png)`
7. Credits: "Built by **Sami Malik** using **Claude** (Anthropic) + **GPT-4o** (OpenAI) via [Project Factory](https://github.com/{settings.github_username})"

Tone: friendly, impressive, easy to scan. Use proper markdown."""

    log("📝 Claude writing README...")
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
