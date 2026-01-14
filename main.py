import pygame
import sys

# Configuration
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
BACKGROUND_COLOR = (0, 0, 0)  # Pure black

def main():
    pygame.init()
    
    # Try fullscreen on Pi, windowed on Mac for development
    try:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    except:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    
    pygame.display.set_caption("Skylight")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    
    # Main loop
    running = True
    frame = 0
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
        
        # Clear screen
        screen.fill(BACKGROUND_COLOR)
        
        # Draw a test circle that moves - proves rendering works
        x = (frame * 2) % SCREEN_WIDTH
        pygame.draw.circle(screen, (50, 50, 80), (x, SCREEN_HEIGHT // 2), 20)
        
        pygame.display.flip()
        clock.tick(30)  # 30 FPS
        frame += 1
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()