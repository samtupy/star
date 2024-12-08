import mistune
import os
readme_md = ""
with open(os.path.join(os.path.split(__file__)[0], "readme.md"), "r") as f: readme_md = f.read()
with open(os.path.join(os.path.split(__file__)[0], "readme.html"), "w") as f: f.write(f"<html>\n<head>\n<title>STAR user client documentation</title>\n</head>\n<body>\n{mistune.html(readme_md)}\n</body>\n</html>\n")
