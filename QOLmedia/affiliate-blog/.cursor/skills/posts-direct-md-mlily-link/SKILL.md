---
name: posts-direct-md-mlily-link
description: >-
  In `content/posts/*.md` (only the files directly under `content/posts/`), adds
  a Markdown hyperlink to the word `エムリリー` using the provided URL. Use
  this when the user asks to target "posts直下の.md" (or "直下のみ") and link
  `エムリリー` to `https://px.a8.net/svt/ejp?a8mat=4AZS0R+87WHZ6+3QJC+BWVTE`.
---

# posts-direct-md-mlily-link

## Instructions
1. Target files: `content/posts/*.md` (non-recursive; only files directly under `content/posts/`).
2. For each target file:
   - Search for the plain text `エムリリー`.
   - Replace `エムリリー` with `[エムリリー](https://px.a8.net/svt/ejp?a8mat=4AZS0R+87WHZ6+3QJC+BWVTE)` only when the occurrence is not already inside an existing Markdown link label (i.e., not immediately preceded by `[`).
3. Keep everything else unchanged.

## Command (recommended)
Use `perl` with a negative lookbehind to avoid double-linking.

```bash
perl -pi -e 's/(?<!\\[)エムリリー/[エムリリー](https:\\/\\/px.a8.net\\/svt\\/ejp?a8mat=4AZS0R+87WHZ6+3QJC+BWVTE)/g' content/posts/*.md
```

