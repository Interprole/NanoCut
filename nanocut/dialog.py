"""Native file pickers run on their own main thread."""

import json
import sys
from tkinter import Tk, filedialog

if __name__ == "__main__":
    config = json.loads(sys.stdin.buffer.read().decode())
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    mode = config.pop("mode")
    action = {
        "multi": filedialog.askopenfilenames,
        "open": filedialog.askopenfilename,
        "save": filedialog.asksaveasfilename,
    }[mode]
    value = action(parent=root, **config)
    sys.stdout.buffer.write(json.dumps(value).encode())
    root.destroy()
