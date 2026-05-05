import subprocess

subprocess.run(["systemd-run", "--user", "--quiet", "gnome-calculator"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
