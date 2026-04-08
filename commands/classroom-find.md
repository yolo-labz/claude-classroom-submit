---
description: Search Pedro's active Google Classroom courses for assignments matching a query string. Returns a table of `course_id`, `coursework_id`, `due_date`, `course_name`, and `title` for every assignment whose title or description contains the query (case-insensitive). Use this as the first step before submitting a file, to discover the IDs needed for `/classroom-submit`. Without arguments, the command prints a usage reminder.
argument-hint: <search-query>
---

# /classroom-find

Search all active courses for coursework matching the query.

```bash
query="$ARGUMENTS"
if [ -z "$query" ]; then
  echo "Usage: /classroom-find <search-query>"
  echo "Example: /classroom-find Airbnb"
  exit 0
fi
"${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh" find "$query" --terse
```

**Output format** (tab-separated):

```
<course_id>    <coursework_id>    <due_date>    <course_name>            <title>
ODUxMzc0NzU3   Nzk3MDIxMjk3      2026-04-07    AD432 - Estratégia...   Atividade 2 - O caso da empresa Airbnb
```

**Typical follow-up:**

```bash
# Once you know the IDs, submit with:
/classroom-submit ~/Documents/Notes/.../atividade2-airbnb.pdf Airbnb
# or with explicit IDs:
classroom-lib.sh submit-file ~/file.pdf --course ODUxMzc0NzU3 --coursework Nzk3MDIxMjk3
```

**If the query matches nothing:** try a shorter / broader term. The search is a plain case-insensitive substring match against both the title and description. Very short queries (`"a"`, `"1"`) will match too much — aim for at least 4–5 distinctive characters.
