import socket, threading, sys, time

HOST = '127.0.0.1'  # O endereço IP do servidor (Roteador B)
PORT = 55555        # A mesma porta usada pelo servidor

# --- Configurações do Go-Back-N ---
WINDOW_SIZE = 5     # Tamanho da janela (N)
SEQ_MODULO = 10     # Espaço de num de sequência (deve ser > N, ex: 2*N)
TIMEOUT = 5.0       # Tempo de timeout em segundos

# --- Variáveis de Estado ---
base = 0            # Num de sequência do pacote mais antigo não confirmado
next_seq_num = 0    # Num de sequência do próximo pacote a ser enviado
timer = None        # Objeto Timer
lock = threading.Lock() # Lock para proteger as variáveis de estado
packet_buffer = {}  # Buffer para pacotes enviados mas não confirmados (ACK)

server_socket = None # Socket global

def deconectar(conn):
    global timer
    if timer:
        timer.cancel()
    if conn:
        conn.close()
    print("Conexão encerrada.")
    sys.exit(0)

def start_timer():
    """Inicia (ou reinicia) o timer global."""
    global timer
    if timer:
        timer.cancel()
    timer = threading.Timer(TIMEOUT, handle_timeout)
    timer.daemon = True # Permite que o programa saia mesmo se o timer estiver ativo
    timer.start()

def stop_timer():
    """Para o timer global."""
    global timer
    if timer:
        timer.cancel()
    timer = None

def handle_timeout():
    """Lida com o evento de timeout (reenvia toda a janela)."""
    with lock:
        print(f"\n--- TIMEOUT! (Base={base}, Next={next_seq_num}) ---")
        print(f"Reenviando pacotes de {base} até {next_seq_num-1}...")
        
        current = base
        while True:
            # Lógica para iterar de 'base' até 'next_seq_num' com wraparound
            if current == next_seq_num:
                break
                
            pkt = packet_buffer.get(current)
            if pkt:
                print(f"Reenviando: {pkt}")
                server_socket.sendto(pkt.encode('UTF-8'), (HOST, PORT))
            
            current = (current + 1) % SEQ_MODULO
            
            # Condição de parada caso base == next_seq_num (janela vazia, não deveria acontecer no timeout)
            if current == base: 
                break

        # Reinicia o timer se ainda houver pacotes em trânsito
        if base != next_seq_num:
            start_timer()

def is_new_ack(ack_num):
    """Verifica se um ACK é novo (está dentro da janela atual)."""
    # Lida com o wraparound (ex: base=8, next=2, janela é 8, 9, 0, 1)
    if base < next_seq_num:
        # Sem wraparound: base <= ack_num < next_seq_num
        return base <= ack_num < next_seq_num
    else:
        # Com wraparound: (base <= ack_num) OR (ack_num < next_seq_num)
        return base <= ack_num or ack_num < next_seq_num

def receber(conn):
    """Thread para receber ACKs do roteador."""
    global base, timer, next_seq_num
    while True:
        try:
            mensagem, addr = conn.recvfrom(4096)   
            if not mensagem:
                continue

            msg_str = mensagem.decode('UTF-8')
            
            # Processa apenas ACKs
            if msg_str.startswith("ACK:"):
                try:
                    ack_num = int(msg_str.split(":")[1])
                    print(f"\n[PC1] Recebeu ACK: {ack_num}")

                    if is_new_ack(ack_num):
                        with lock:
                            # ACK Cumulativo: Libera todos até ack_num
                            new_base = (ack_num + 1) % SEQ_MODULO
                            
                            # Limpa o buffer dos pacotes confirmados
                            current_ack = base
                            while True:
                                if current_ack == new_base:
                                    break
                                packet_buffer.pop(current_ack, None) # Remove do buffer
                                current_ack = (current_ack + 1) % SEQ_MODULO

                            base = new_base
                            print(f"[PC1] Janela avançou. Nova Base: {base}")
                            
                            if base == next_seq_num:
                                # Todos os pacotes foram confirmados
                                stop_timer()
                                print(f"[PC1] Janela vazia. Timer parado.")
                            else:
                                # Ainda há pacotes em trânsito
                                start_timer()
                                print(f"[PC1] Timer reiniciado.")
                    else:
                         print(f"[PC1] ACK duplicado/antigo {ack_num} (Base={base}). Ignorado.")

                except (ValueError, IndexError):
                    print(f"\n[PC1] Recebeu ACK mal formatado (corrompido?): {msg_str}")
                except Exception as e:
                    print(f"Erro ao processar ACK: {e}")

        except Exception as e:
            print(f"\nErro ao receber mensagem: {e}")
            deconectar(conn)
            break

# --- Programa Principal (Remetente) ---
try:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Envia um pacote inicial para o roteador aprender o endereço de PC1
    server_socket.sendto(b"INIT_PC1", (HOST, PORT))
    print("[PC1] Remetente RDT (Go-Back-N) iniciado.")
    print("[PC1] Enviando pacote de inicialização para o Roteador B.")

    # Inicia a thread de recebimento de ACKs
    thread_receber = threading.Thread(target=receber, args=(server_socket,))
    thread_receber.daemon = True
    thread_receber.start()

    while True:
        # Verifica se a janela está cheia
        with lock:
            # Lógica de janela cheia com wraparound
            window_full = (next_seq_num == (base + WINDOW_SIZE) % SEQ_MODULO)

        if window_full:
            print(f"--- Janela cheia (Base={base}, Next={next_seq_num}). Esperando ACKs... ---")
            time.sleep(1) # Espera antes de verificar a janela novamente
            continue
        
        # Se a janela não está cheia, solicita dados
        mensagem = input("Digite a mensagem a ser enviada (ou 'exit' para sair): ")
        if mensagem.lower() == 'exit':
            break

        with lock:
            # Cria e armazena o pacote
            pkt_str = f"SEQ:{next_seq_num}:{mensagem}"
            packet_buffer[next_seq_num] = pkt_str
            
            # Envia o pacote
            server_socket.sendto(pkt_str.encode('UTF-8'), (HOST, PORT))
            print(f"[PC1] Enviou: {pkt_str} (Base={base})")

            # Se a janela estava vazia (base == next_seq_num), inicia o timer
            if base == next_seq_num:
                print(f"[PC1] Timer iniciado.")
                start_timer()
            
            # Avança o próximo número de sequência
            next_seq_num = (next_seq_num + 1) % SEQ_MODULO

except (ConnectionAbortedError, ConnectionRefusedError, ConnectionResetError) as e:
    print(f"Erro de conexão: {e}")
except KeyboardInterrupt:
    print("\nEncerrando remetente...")
finally:
    deconectar(server_socket)