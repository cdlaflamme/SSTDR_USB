#pipetest.py
import sys

input = sys.stdin.buffer.read(100)
print("received from stdin: ")
print(input)