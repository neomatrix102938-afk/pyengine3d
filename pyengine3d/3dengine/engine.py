import curses
import math
import socket
import threading
import time

# Store remote player positions & chat log
other_players = {}
chat_log = ["System: Welcome! Press 't' or '/' to chat or enter commands."]

# --- 3D SCENE DISTANCE FUNCTIONS (SDF) ---
def map_scene(px, py, pz):
    # 1. Ground Plane (y = -1.0)
    d_plane = py - (-1.0)

    # 2. Sphere at (-2.2, 0.0, 6.0) with radius 1.2
    sx, sy, sz = px - (-2.2), py - 0.0, pz - 6.0
    d_sphere = math.sqrt(sx*sx + sy*sy + sz*sz) - 1.2

    # 3. Cube at (2.2, 0.0, 6.0) with side size 1.0
    cx = abs(px - 2.2) - 1.0
    cy = abs(py - 0.0) - 1.0
    cz = abs(pz - 6.0) - 1.0
    d_cube = max(cx, max(cy, cz))

    # Find closest object
    closest_dist = d_plane
    obj_id = 1 # Plane

    if d_sphere < closest_dist:
        closest_dist = d_sphere
        obj_id = 2 # Sphere

    if d_cube < closest_dist:
        closest_dist = d_cube
        obj_id = 3 # Cube

    # 4. Other Players (Represented as small spheres)
    for p_id, pos in list(other_players.items()):
        op_x, op_y, op_z = pos
        dx, dy, dz = px - op_x, py - op_y, pz - op_z
        d_player = math.sqrt(dx*dx + dy*dy + dz*dz) - 0.5
        if d_player < closest_dist:
            closest_dist = d_player
            obj_id = 4 # Other Player

    return closest_dist, obj_id


# --- NETWORKING HELPERS ---
def run_server(port=5555):
    """Runs a local host server to sync player positions and chat messages."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", port))
    server.listen(5)
    clients = []

    def handle_client(conn, client_id):
        while True:
            try:
                data = conn.recv(1024).decode('utf-8')
                if not data:
                    break
                # Broadcast data to all other clients
                for c, cid in clients:
                    if cid != client_id:
                        try:
                            c.sendall(data.encode('utf-8'))
                        except:
                            pass
            except:
                break
        conn.close()

    cid_counter = 0
    while True:
        conn, _ = server.accept()
        cid_counter += 1
        clients.append((conn, cid_counter))
        threading.Thread(target=handle_client, args=(conn, cid_counter), daemon=True).start()


def network_listener(sock):
    """Listens for incoming network packets (position updates and chat)."""
    global other_players, chat_log
    buffer = ""
    while True:
        try:
            data = sock.recv(1024).decode('utf-8')
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.startswith("POS"):
                    parts = line.split()
                    p_id = parts[1]
                    x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                    other_players[p_id] = (x, y, z)
                elif line.startswith("CHAT"):
                    msg = line[5:]
                    chat_log.append(msg)
                    if len(chat_log) > 5:
                        chat_log.pop(0)
        except:
            break


# --- COMMAND PARSER ---
def handle_command(cmd_str, cam_pos):
    """Parses and executes slash commands."""
    cam_x, cam_y, cam_z = cam_pos
    parts = cmd_str.strip().split()
    if not parts:
        return cam_x, cam_y, cam_z

    cmd = parts[0].lower()

    if cmd == "/kill":
        chat_log.append("System: Player respawned at (0, 0.5, 0).")
        return 0.0, 0.5, 0.0

    elif cmd == "/tp":
        if len(parts) == 4:
            try:
                tx, ty, tz = float(parts[1]), float(parts[2]), float(parts[3])
                chat_log.append(f"System: Teleported to ({tx:.1f}, {ty:.1f}, {tz:.1f}).")
                return tx, ty, tz
            except ValueError:
                chat_log.append("System: Invalid coordinates for /tp!")
        else:
            chat_log.append("System: Usage: /tp <x> <y> <z>")

    elif cmd == "/help":
        chat_log.append("Commands: /tp <x> <y> <z>, /kill, /help")

    else:
        chat_log.append(f"System: Unknown command '{cmd}'. Type /help for options.")

    if len(chat_log) > 5:
        chat_log.pop(0)

    return cam_x, cam_y, cam_z


# --- CHAT INPUT OVERLAY ---
def prompt_chat_input(stdscr, initial_char=""):
    """Displays an input prompt overlay at the bottom of the screen."""
    h, w = stdscr.getmaxyx()
    input_str = initial_char
    curses.echo()
    curses.curs_set(1)

    stdscr.addstr(h - 1, 0, " " * (w - 1))
    stdscr.addstr(h - 1, 2, f"Say/Command: {input_str}", curses.A_BOLD)
    stdscr.refresh()

    while True:
        ch = stdscr.getch()
        if ch in [10, 13]: # Enter key
            break
        elif ch in [27]: # ESC key to cancel
            input_str = ""
            break
        elif ch in [curses.KEY_BACKSPACE, 127, 8]:
            input_str = input_str[:-1]
        elif 32 <= ch <= 126:
            input_str += chr(ch)

        stdscr.addstr(h - 1, 0, " " * (w - 1))
        stdscr.addstr(h - 1, 2, f"Say/Command: {input_str}", curses.A_BOLD)
        stdscr.refresh()

    curses.noecho()
    curses.curs_set(0)
    return input_str.strip()


# --- RENDERER ---
def render_3d(stdscr, sock, player_id):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(30)

    # Colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_YELLOW, -1)   # Plane
    curses.init_pair(2, curses.COLOR_CYAN, -1)     # Sphere
    curses.init_pair(3, curses.COLOR_GREEN, -1)    # Cube
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)  # Remote Player
    curses.init_pair(5, curses.COLOR_WHITE, -1)    # UI / Text

    # Position & Orientation
    cam_x, cam_y, cam_z = 0.0, 0.5, 0.0
    yaw = 0.0
    pitch = 0.0

    # Textures
    SHADE_CUBE = ["█", "▓", "▒", "░", "#", "+", ":"]
    SHADE_SPHERE = ["@", "O", "o", "*", "·", "."]
    SHADE_PLAYER = ["M", "W", "8", "0", "*", "."]

    last_net_sync = 0

    while True:
        h, w = stdscr.getmaxyx()
        render_w = min(w - 2, 70)
        render_h = min(h - 12, 18)

        if render_w < 30 or render_h < 8:
            stdscr.clear()
            stdscr.addstr(0, 0, "Terminal window too small! Please enlarge window.")
            stdscr.refresh()
            time.sleep(0.1)
            continue

        buffer = [[(" ", 5) for _ in range(render_w)] for _ in range(render_h)]

        # --- RAYMARCHING ---
        fov = 1.0
        aspect = render_h / float(render_w)

        for sc_y in range(render_h):
            vy = (1.0 - 2.0 * (sc_y / float(render_h))) * aspect * fov

            for sc_x in range(render_w):
                vx = (2.0 * (sc_x / float(render_w)) - 1.0) * fov

                # Apply yaw (horizontal rotation) and pitch (vertical rotation)
                rx = vx
                ry = vy * math.cos(pitch) - 1.0 * math.sin(pitch)
                rz = vy * math.sin(pitch) + 1.0 * math.cos(pitch)

                dir_x = rx * math.cos(yaw) + rz * math.sin(yaw)
                dir_y = ry
                dir_z = -rx * math.sin(yaw) + rz * math.cos(yaw)

                length = math.sqrt(dir_x*dir_x + dir_y*dir_y + dir_z*dir_z)
                dir_x /= length
                dir_y /= length
                dir_z /= length

                t = 0.0
                hit = False
                hit_obj = 0

                for _ in range(35):
                    px = cam_x + dir_x * t
                    py = cam_y + dir_y * t
                    pz = cam_z + dir_z * t

                    dist, obj_id = map_scene(px, py, pz)

                    if dist < 0.04:
                        hit = True
                        hit_obj = obj_id
                        break

                    t += dist
                    if t > 20.0:
                        break

                if hit:
                    if hit_obj == 1:
                        px = cam_x + dir_x * t
                        pz = cam_z + dir_z * t
                        checker = (int(math.floor(px)) + int(math.floor(pz))) % 2
                        char = "#" if checker == 0 else "."
                        color = 1 if checker == 0 else 5
                        buffer[sc_y][sc_x] = (char, color)

                    elif hit_obj == 2:
                        idx = min(len(SHADE_SPHERE) - 1, int(t / 2.5))
                        buffer[sc_y][sc_x] = (SHADE_SPHERE[idx], 2)

                    elif hit_obj == 3:
                        idx = min(len(SHADE_CUBE) - 1, int(t / 2.5))
                        buffer[sc_y][sc_x] = (SHADE_CUBE[idx], 3)

                    elif hit_obj == 4:
                        idx = min(len(SHADE_PLAYER) - 1, int(t / 2.5))
                        buffer[sc_y][sc_x] = (SHADE_PLAYER[idx], 4)

        # --- DRAW FRAME ---
        stdscr.erase()
        stdscr.addstr(0, 2, "=== MULTIPLAYER 3D RAYMARCHER ===", curses.A_BOLD | curses.color_pair(5))
        stdscr.addstr(1, 2, f"ID: {player_id} | Pos: ({cam_x:.1f}, {cam_y:.1f}, {cam_z:.1f}) | Players: {len(other_players)+1}", curses.color_pair(5))

        # Viewport
        for y in range(render_h):
            for x in range(render_w):
                char, color_pair = buffer[y][x]
                stdscr.addstr(y + 3, x + 2, char, curses.color_pair(color_pair))

        # Controls & Info
        stdscr.addstr(render_h + 4, 2, "Controls: [WASD] Walk/Strafe  |  [ARROWS] Camera  |  [T / /] Chat/Command", curses.A_DIM)

        # Chat Log Box
        stdscr.addstr(render_h + 6, 2, "--- CHAT & SYSTEM MESSAGES ---", curses.A_BOLD)
        for idx, line in enumerate(chat_log[-4:]):
            stdscr.addstr(render_h + 7 + idx, 2, line[:render_w])

        stdscr.refresh()

        # Network position broadcast
        now = time.time()
        if sock and (now - last_net_sync > 0.05):
            try:
                msg = f"POS {player_id} {cam_x:.2f} {cam_y:.2f} {cam_z:.2f}\n"
                sock.sendall(msg.encode('utf-8'))
                last_net_sync = now
            except:
                pass

        # --- INPUT HANDLING ---
        key = stdscr.getch()
        move_speed = 0.25
        turn_speed = 0.12

        if key in [ord('q'), ord('Q')]:
            break
        elif key in [ord('t'), ord('T'), ord('/')]:
            start_prefix = "/" if key == ord('/') else ""
            user_input = prompt_chat_input(stdscr, start_prefix)
            if user_input:
                if user_input.startswith("/"):
                    cam_x, cam_y, cam_z = handle_command(user_input, (cam_x, cam_y, cam_z))
                else:
                    formatted_msg = f"{player_id[:8]}: {user_input}"
                    chat_log.append(formatted_msg)
                    if len(chat_log) > 5:
                        chat_log.pop(0)
                    if sock:
                        try:
                            sock.sendall(f"CHAT {formatted_msg}\n".encode('utf-8'))
                        except:
                            pass

        # WASD Movement
        elif key in [ord('w'), ord('W')]:
            cam_x += math.sin(yaw) * move_speed
            cam_z += math.cos(yaw) * move_speed
        elif key in [ord('s'), ord('S')]:
            cam_x -= math.sin(yaw) * move_speed
            cam_z -= math.cos(yaw) * move_speed
        elif key in [ord('a'), ord('A')]:
            cam_x -= math.cos(yaw) * move_speed
            cam_z += math.sin(yaw) * move_speed
        elif key in [ord('d'), ord('D')]:
            cam_x += math.cos(yaw) * move_speed
            cam_z -= math.sin(yaw) * move_speed

        # Arrow Keys Camera Rotation
        elif key == curses.KEY_LEFT:
            yaw -= turn_speed
        elif key == curses.KEY_RIGHT:
            yaw += turn_speed
        elif key == curses.KEY_UP:
            pitch = min(1.0, pitch + turn_speed)
        elif key == curses.KEY_DOWN:
            pitch = max(-1.0, pitch - turn_speed)


# --- ENTRY POINT ---
def main():
    print("=== MULTIPLAYER TERMINAL 3D ===")
    choice = input("1. Host Server & Join\n2. Join Server (via IP/Hostname)\nSelect (1 or 2): ").strip()

    player_id = socket.gethostname() + "_" + str(int(time.time() % 1000))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if choice == "1":
        threading.Thread(target=run_server, daemon=True).start()
        time.sleep(0.5)
        target_ip = "127.0.0.1"
    else:
        target_ip = input("Enter host IP address or Hostname: ").strip()

    try:
        sock.connect((target_ip, 5555))
        threading.Thread(target=network_listener, args=(sock,), daemon=True).start()
        print("Connected! Launching...")
        time.sleep(1)
    except Exception as e:
        print(f"Could not connect to target host: {e}")
        return

    curses.wrapper(lambda stdscr: render_3d(stdscr, sock, player_id))


if __name__ == "__main__":
    main()
