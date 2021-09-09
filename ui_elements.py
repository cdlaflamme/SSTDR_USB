#ui_elements.py
#UI elements primarily designed for SSTDR_USB GUI but technocally function agnostic

import pygame

class Button:
    #static list of all buttons, used for drawing/colission checking
    buttons = []
    
    def __init__(self, text, font, fxn, color_bg=(0,0,200), color_highlight=(255,140,0), color_text=(225,225,225), text_padding=5, x=0, y=0):
        #add to list of all buttons
        self.buttons.append(self)
        #label and function
        self.text = text
        self.function = fxn
        #ui elements
        self.color_bg = color_bg
        self.color_highlight = color_highlight
        self.color_text = color_text
        self.text_padding = text_padding
        self.size = list(font.size(text))
        self.size[0] += 2*text_padding
        self.size[1] += 2*text_padding
        self.size_x = self.size[0]
        self.size_y = self.size[1]
        self.surf = pygame.Surface(self.size)
        self.text_surf = font.render(text, True, color_text)
        self.rect = pygame.Rect(x, y, self.size_x, self.size_y)
        self.set_highlight(False)
        
    def move(self, x, y):
        self.rect.x = x
        self.rect.y = y
        
    def set_highlight(self, highlight=True):
        if highlight:
            self.surf.fill(self.color_highlight)
        else:
            self.surf.fill(self.color_bg)
        self.surf.blit(self.text_surf,(self.text_padding, self.text_padding))
