# -*- coding: utf-8 -*-
"""
Created on Tue Oct 15 17:24:33 2019

@author: Cody
"""
# Clear the screen and hold it for 3 seconds
import curses
import sys

screen = curses.initscr()
print("Opening scanner interactive window...")

curses.noecho()
curses.cbreak()

screen.clear()
screen.addstr(1,0,"Scanning. Press q to halt.")
screen.addstr(2,0,"Detected key: ")
#screen.addstr(3,0,"Received from stdin: ")

screen.refresh()

while(True):
    c = screen.getch()
    screen.addch(2,15,c)
    
    #input = sys.stdin.read(5)
    #screen.addstr(4,0,input)
    
    screen.refresh()
    
    if (c == ord('q')):
        break

curses.nocbreak()
curses.echo()
curses.endwin()