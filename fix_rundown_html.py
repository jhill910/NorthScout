"""Fix THE RUNDOWN cards rendering their HTML as code blocks.

WHAT WENT WRONG
---------------
The card HTML was written as an indented triple-quoted f-string, which reads
nicely in the source. But Streamlit renders markdown first, and markdown
treats any line indented four or more spaces as a literal code block. So the
opening <div> (at column 0) became a real element and everything after it --
the logo, headline and timestamp -- was displayed as source code inside it.

The fix is to emit the HTML with no leading whitespace on any line. Built as
a list of fragments joined with "", so the source stays readable while the
output is a single unindented line that markdown passes straight through.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")

EMPTY_OLD = '''            st.markdown(
                f"""<div style="background:{_a['bg_color']};border-radius:10px;padding:14px;
                       min-height:150px;"><div style="color:{_a['text_color']};font-weight:700;
                       font-size:13px;letter-spacing:0.06em;">{_team.split()[-1].upper()}</div>
                       <div style="color:#c9d1d9;font-size:13px;margin-top:10px;">
                       No stories in the current snapshot.</div></div>""",
                unsafe_allow_html=True)
'''

EMPTY_NEW = '''            # NOTE: no leading whitespace inside the emitted HTML -- markdown
            # turns any 4-space-indented line into a code block.
            st.markdown("".join([
                f"<div style=\\"background:{_a['bg_color']};border-radius:10px;",
                "padding:14px;min-height:150px;\\">",
                f"<div style=\\"color:{_a['text_color']};font-weight:700;font-size:13px;",
                f"letter-spacing:0.06em;\\">{_team.split()[-1].upper()}</div>",
                "<div style=\\"color:#c9d1d9;font-size:13px;margin-top:10px;\\">",
                "No stories in the current snapshot.</div></div>",
            ]), unsafe_allow_html=True)
'''

CARD_OLD = '''        st.markdown(
            f"""<div style="background:{_a['bg_color']};border-radius:10px;padding:14px;
                   min-height:150px;box-shadow:0 0 12px {_a['glow']};">
                 <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                   <img src="{_a['logo']}" style="height:22px;width:22px;object-fit:contain;">
                   <span style="color:{_a['text_color']};font-weight:700;font-size:12px;
                          letter-spacing:0.06em;">{_team.split()[-1].upper()}</span>
                 </div>
                 {_img}
                 {_headline}
                 <div style="color:#8b949e;font-size:11px;margin-top:8px;">{_when}</div>
               </div>""",
            unsafe_allow_html=True)
'''

CARD_NEW = '''        # NOTE: every fragment below must stay free of leading whitespace.
        # Streamlit renders markdown before HTML, and markdown turns any line
        # indented four spaces or more into a code block -- which is exactly
        # what happened to the first version of this card.
        st.markdown("".join([
            f"<div style=\\"background:{_a['bg_color']};border-radius:10px;padding:14px;",
            f"min-height:150px;box-shadow:0 0 12px {_a['glow']};\\">",
            "<div style=\\"display:flex;align-items:center;gap:8px;margin-bottom:10px;\\">",
            f"<img src=\\"{_a['logo']}\\" style=\\"height:22px;width:22px;object-fit:contain;\\">",
            f"<span style=\\"color:{_a['text_color']};font-weight:700;font-size:12px;",
            f"letter-spacing:0.06em;\\">{_team.split()[-1].upper()}</span>",
            "</div>",
            _img,
            _headline,
            f"<div style=\\"color:#8b949e;font-size:11px;margin-top:8px;\\">{_when}</div>",
            "</div>",
        ]), unsafe_allow_html=True)
'''

EDITS = [("empty-state card", EMPTY_OLD, EMPTY_NEW),
         ("story card", CARD_OLD, CARD_NEW)]


def main():
    write = "--write" in sys.argv
    if not os.path.exists(APP):
        print("ERROR: app.py not found. Run this from inside the repo.")
        return 1
    text = open(APP, encoding="utf-8").read()

    if 'st.markdown("".join([' in text:
        print("   note: already patched.")
        return 1

    print("Checking app.py anchors:")
    bad = []
    for name, find, _ in EDITS:
        n = text.count(find)
        print(f"   {'ok ' if n == 1 else 'BAD'} {name:<20} anchor found {n}x")
        if n != 1:
            bad.append(name)
    if bad:
        print("\nSTOPPED -- nothing changed. Send this output back.")
        return 1

    for _, find, repl in EDITS:
        text = text.replace(find, repl)

    if not write:
        print("\nAnchors matched. Re-run with --write to apply.")
        return 0

    shutil.copyfile(APP, APP + ".bak2")
    with open(APP, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("\n   applied. Backup: app.py.bak2")
    print("\n   python -m streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
