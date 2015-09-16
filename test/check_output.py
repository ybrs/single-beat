files = ['first_single_beat.log', 'second_single_beat.log', 'third_single_beat.log']

hello_cnt = 0
for fname in files:
    f = open(fname)
    if 'hello - ' in f.read():
        hello_cnt += 1

assert hello_cnt == 1
