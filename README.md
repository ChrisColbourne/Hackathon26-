# Hackathon26-
Tutor Robot: Detects errors in equation solving and notifies the user in real time

An otter tutor watches a whiteboard through a webcam. When the student makes a
mistake (wrong rule, misapplied rule, arithmetic slip) it says so out loud and
points a laser at the line, without ever giving away the fix.

- **Plan, roles, message contracts, timeline:** [docs/GAMEPLAN.md](docs/GAMEPLAN.md)
- **The brain (Gemini + OpenCV/C++ + SymPy, laptop server):** [brain/README.md](brain/README.md)

Quick start:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r brain/requirements.txt
cp .env.example .env                       # add GEMINI_API_KEY
python -m brain.run_cli --camera --show --mock   # no Gemini quota needed
```
