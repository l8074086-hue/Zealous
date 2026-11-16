import pygame
import threading
from collections import deque
from typing import Optional

GRID_SIZE = 20
SCREEN_SIZE = (1000, 800)
MAX_X = (SCREEN_SIZE[0] // GRID_SIZE) - 1
MAX_Y = (SCREEN_SIZE[1] // GRID_SIZE) - 1
MOVE_SPEED = 5

BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
GREY  = (40, 40, 40)
RED   = (255, 0, 0)

cyno_x, cyno_y = 0, 0
player_x, player_y = 40, 40
cyno_draw_x, cyno_draw_y = 0.0, 0.0
player_draw_x, player_draw_y = 0.0, 0.0
follow_mode = False
game_running = False
_game_instance: Optional[threading.Thread] = None

player_trail = deque(maxlen=20)
move_timer = 0


def move_cyno(direction, steps=1):
    global cyno_x, cyno_y
    direction = direction.lower()
    for _ in range(steps):
        if direction == "up" and cyno_y > 0:
            cyno_y -= 1
        elif direction == "down" and cyno_y < MAX_Y:
            cyno_y += 1
        elif direction == "left" and cyno_x > 0:
            cyno_x -= 1
        elif direction == "right" and cyno_x < MAX_X:
            cyno_x += 1


def try_hug():
    global cyno_x, cyno_y, player_x, player_y
    dx = abs(cyno_x - player_x)
    dy = abs(cyno_y - player_y)
    if (dx == 1 and dy == 0) or (dx == 0 and dy == 1):
        cyno_x, player_x = player_x, cyno_x
        cyno_y, player_y = player_y, cyno_y
        return True
    return False


def dance():
    global cyno_x, cyno_y
    for _ in range(5):
        cyno_x += 1
        cyno_y += 1
        cyno_x -= 1
        cyno_y -= 1


def _smooth_step(current, target, speed):
    if current < target:
        return min(current + speed, target)
    if current > target:
        return max(current - speed, target)
    return current


def run_game():
    global cyno_draw_x, cyno_draw_y, player_draw_x, player_draw_y
    global player_x, player_y, cyno_x, cyno_y, game_running, move_timer, follow_mode

    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Cyno Grid")
    clock = pygame.time.Clock()

    cyno_draw_x, cyno_draw_y = cyno_x * GRID_SIZE, cyno_y * GRID_SIZE
    player_draw_x, player_draw_y = player_x * GRID_SIZE, player_y * GRID_SIZE
    last_pos = (player_x, player_y)
    game_running = True

    while game_running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game_running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_a and player_x > 0:
                    player_x -= 1
                elif event.key == pygame.K_d and player_x < MAX_X:
                    player_x += 1
                elif event.key == pygame.K_w and player_y > 0:
                    player_y -= 1
                elif event.key == pygame.K_s and player_y < MAX_Y:
                    player_y += 1

        current_pos = (player_x, player_y)
        if current_pos != last_pos:
            player_trail.append(current_pos)
            last_pos = current_pos

        move_timer += 1
        if follow_mode and len(player_trail) >= 5 and move_timer >= 10:
            tx, ty = player_trail[-5]
            if cyno_x < tx:
                cyno_x += 1
            elif cyno_x > tx:
                cyno_x -= 1
            if cyno_y < ty:
                cyno_y += 1
            elif cyno_y > ty:
                cyno_y -= 1
            move_timer = 0

        target_cx, target_cy = cyno_x * GRID_SIZE, cyno_y * GRID_SIZE
        cyno_draw_x = _smooth_step(cyno_draw_x, target_cx, MOVE_SPEED)
        cyno_draw_y = _smooth_step(cyno_draw_y, target_cy, MOVE_SPEED)

        target_px, target_py = player_x * GRID_SIZE, player_y * GRID_SIZE
        player_draw_x = _smooth_step(player_draw_x, target_px, MOVE_SPEED)
        player_draw_y = _smooth_step(player_draw_y, target_py, MOVE_SPEED)

        screen.fill(BLACK)

        for x in range(0, SCREEN_SIZE[0], GRID_SIZE):
            pygame.draw.line(screen, GREY, (x, 0), (x, SCREEN_SIZE[1]))
        for y in range(0, SCREEN_SIZE[1], GRID_SIZE):
            pygame.draw.line(screen, GREY, (0, y), (SCREEN_SIZE[0], y))

        pygame.draw.rect(screen, GREEN, (cyno_draw_x, cyno_draw_y, GRID_SIZE, GRID_SIZE))
        pygame.draw.rect(screen, RED, (player_draw_x, player_draw_y, GRID_SIZE, GRID_SIZE))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def start_game_thread():
    global _game_instance
    if _game_instance is None or not _game_instance.is_alive():
        _game_instance = threading.Thread(target=run_game, daemon=True)
        _game_instance.start()


def is_game_active():
    game_thread = _game_instance
    return game_running or (game_thread is not None and game_thread.is_alive())
