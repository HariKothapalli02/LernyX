import requests

def test_wandbox(lang, code, stdin=""):
    compiler_map = {
        "python": "cpython-3.12.7",
        "java": "openjdk-jdk-22+36",
        "c": "gcc-13.2.0-c"
    }
    compiler = compiler_map.get(lang, "cpython-3.12.7")
    payload = {
        "compiler": compiler,
        "code": code,
        "stdin": stdin
    }
    try:
        r = requests.post("https://wandbox.org/api/compile.json", json=payload, timeout=10)
        res = r.json()
        out = res.get("program_output", "") or res.get("compiler_error", "") or res.get("program_error", "")
        print(f"[{lang}] Success (status {r.status_code}): {out.strip()}")
    except Exception as e:
        print(f"[{lang}] Failed: {e}")

if __name__ == "__main__":
    test_wandbox("python", "print('hello python')")
    test_wandbox("c", '#include <stdio.h>\nint main() { printf("hello c\\n"); return 0; }')
    test_wandbox("java", 'public class Main { public static void main(String[] args) { System.out.println("hello java"); } }')
