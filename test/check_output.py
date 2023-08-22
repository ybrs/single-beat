files = [
    "first_single_beat.log",
    "second_single_beat.log",
    "third_single_beat.log"
]

hello_cnt = 0
for fname in files:
    try:
        f = open(fname)
        if "hello - " in f.read():
            hello_cnt += 1
    except OSError:
        pass

assert hello_cnt == 1
