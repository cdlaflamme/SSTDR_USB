#PV_GUI_mockup.py
import sys, os, pygame

#constants
SCREEN_SIZE = SCREEN_X, SCREEN_Y = 900, 700
TERMINAL_Y = 200
VISUAL_Y = SCREEN_Y - TERMINAL_Y
BORDER_WIDTH = 3
BORDER_PADDING = 2

COLOR_WHITE     = (225, 225, 225)
COLOR_GREY      = (128, 128, 128)
COLOR_ORANGE    = (255, 140,   0)
COLOR_BLUE      = (  0,   0, 200)
COLOR_BLACK     = ( 10,  10,  10)

BG_COLOR = COLOR_GREY
TERMINAL_COLOR = COLOR_WHITE
WIRE_COLOR = COLOR_BLUE
TEXT_COLOR = COLOR_BLACK

PANEL_SCALE = 1/6
PANEL_PADDING = (100, 25)
WIRE_WIDTH = 2

#initializing pygame
pygame.init()
screen = pygame.display.set_mode(SCREEN_SIZE)
pygame.display.set_caption("PV Fault Scanner")

#loading assets, preparing pre-baked surfaces
TERMINAL_FONT = pygame.font.Font(None, 40)
STATUS_FONT = pygame.font.Font(None, 20)

panel_surf = pygame.image.load(os.path.join("Assets", "PV_panel_CharlesMJames_CC.jpg"))
panel_surf = pygame.transform.scale(panel_surf, (int(panel_surf.get_width()*PANEL_SCALE), int(panel_surf.get_height()*PANEL_SCALE)))
panel_rect = panel_surf.get_rect()

grass_surf = pygame.image.load(os.path.join("Assets", "grass.png"))
grass_rect = grass_surf.get_rect()

hazard_surf = pygame.image.load(os.path.join("Assets", "hazard.png"))
hazard_rect = hazard_surf.get_rect()

bg_surf = pygame.Surface(screen.get_size())
bg_surf.convert()
bg_rect = bg_surf.get_rect()
bg_surf.fill(BG_COLOR)
"""
for r in range(int(SCREEN_Y / grass_rect.h+1)):
    for c in range(int(SCREEN_X / grass_rect.w+1)):
        bg_surf.blit(grass_surf, grass_rect)
        grass_rect.move_ip(grass_rect.w,0)
    grass_rect.x = 0
    grass_rect.move_ip(0, grass_rect.h)
"""
line_surf = pygame.Surface((SCREEN_X, BORDER_WIDTH))
line_surf.fill(COLOR_ORANGE)
line_rect = line_surf.get_rect()
line_rect.y = VISUAL_Y - BORDER_WIDTH - int(BORDER_PADDING/2)
bg_surf.blit(line_surf, line_rect)
line_surf.fill(COLOR_BLUE)
line_rect.move_ip(0, BORDER_WIDTH + BORDER_PADDING)
bg_surf.blit(line_surf, line_rect)

text_surf = STATUS_FONT.render("Scanning at 24MHz...", True, COLOR_WHITE)
text_rect = text_surf.get_rect()
text_rect.move_ip(3,3)
bg_surf.blit(text_surf, text_rect)

text_surf = STATUS_FONT.render("Selected Array Layout: 'test_panel_layout'", True, COLOR_WHITE)
text_rect = text_surf.get_rect()
text_rect.x = 3
text_rect.bottom = VISUAL_Y - BORDER_WIDTH - int(0.5*BORDER_PADDING) - 3
bg_surf.blit(text_surf, text_rect)

ARRAY_SIZE = (3*(panel_rect.w + PANEL_PADDING[0]), 2*(panel_rect.h + PANEL_PADDING[1]))
array_surf = pygame.Surface(ARRAY_SIZE, pygame.SRCALPHA)
array_surf.convert()
r = 0
PANEL_COORDS = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(0,2)]
PANEL_COORDS.insert(2,(2*(PANEL_PADDING[0] + panel_rect.w), 0.5*(PANEL_PADDING[1] + panel_rect.h)))
r = 1
PANEL_COORDS = PANEL_COORDS + [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(1,-1,-1)]

"""
for r in range(2):
    for c in range(2):
        array_surf.blit(panel_surf, panel_rect)
        panel_rect.move_ip(panel_rect.w + PANEL_PADDING[0],0)
    panel_rect.x = 0
    panel_rect.move_ip(0, panel_rect.h + PANEL_PADDING[1])
panel_rect.move_ip(2*(panel_rect.w + PANEL_PADDING[0]), int(-1.5*(panel_rect.h + PANEL_PADDING[1])))
array_surf.blit(panel_surf, panel_rect)
"""
for p in PANEL_COORDS:
    panel_rect.topleft = p
    array_surf.blit(panel_surf, panel_rect)

array_rect = array_surf.get_rect()
array_rect.center = (int(SCREEN_X*2/3), int(VISUAL_Y/2))

WIRE_COORDS = []
for p in PANEL_COORDS:
    panel_rect.topleft = p
    WIRE_COORDS.append((panel_rect.center[0] + array_rect.topleft[0], panel_rect.center[1] + array_rect.topleft[1]))
WIRE_COORDS.insert(0,(0,WIRE_COORDS[0][1]))
WIRE_COORDS.append((0,WIRE_COORDS[-1][1]))
pygame.draw.lines(bg_surf, WIRE_COLOR, False, WIRE_COORDS, WIRE_WIDTH)

term_surf = pygame.Surface((SCREEN_X, TERMINAL_Y - int(BORDER_PADDING/2) - BORDER_WIDTH))
term_surf.fill(TERMINAL_COLOR)
term_rect = term_surf.get_rect()
term_rect.bottom = SCREEN_Y

#TODO make this more than a placeholder
FAULT = False
FAULT_D_F = 210 #in feet, from SSTDR
FEET_TO_PIXELS = 2.1
FAULT_D_P = int(FAULT_D_F * FEET_TO_PIXELS)

while True:
    #event handling
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            sys.exit()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_f:
                FAULT = not FAULT
    
    #per-frame logic here
    if (FAULT):
        d = 0
        px = WIRE_COORDS[0][0]
        py = WIRE_COORDS[0][1]
        hazard_point = WIRE_COORDS[-1]
        for x,y in WIRE_COORDS[1:]:
            step = ((x-px)**2 + (y-py)**2)**0.5
            if (d+step >= FAULT_D_P):
                hsr = (FAULT_D_P - d)/step #hazard step ratio
                hazard_point = (px + (x-px)*hsr, py + (y-py)*hsr)
                break
            else:
                px = x
                py = y
                d = d + step
        hazard_rect.center = hazard_point
        fault_text_surf = TERMINAL_FONT.render("Open fault located at " + str(FAULT_D_F) + " feet", True, TEXT_COLOR)
    else:
        fault_text_surf = TERMINAL_FONT.render("System OK", True, TEXT_COLOR)
    fault_text_rect = fault_text_surf.get_rect()
    fault_text_rect.center = term_rect.center
    
    #drawing
    screen.blit(bg_surf, bg_rect)
    screen.blit(term_surf, term_rect)
    screen.blit(fault_text_surf, fault_text_rect)
    screen.blit(array_surf, array_rect)
    if (FAULT):
        screen.blit(hazard_surf, hazard_rect)
    pygame.display.flip()
    
    
    
    
    
    
    
    
    