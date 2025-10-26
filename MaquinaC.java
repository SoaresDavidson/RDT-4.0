import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;

public class MaquinaC {
    private static final String HOST = "127.0.0.1";
    private static final int PORT = 55555;
    private static final int BUFFER_SIZE = 4096;
    private static final int WINDOW_SIZE = 5; // Deve ser o mesmo do remetente (pc1.py)
    // O espaço de número de sequência (módulo) é 2 * WINDOW_SIZE
    private static final int SEQ_MODULO = 2 * WINDOW_SIZE; 
    
    private static int expectedSeqNum = 0;
    
    // Camada de aplicação
    private static void deliverData(String data) {
        System.out.println("-> [CAMADA SUPERIOR] Dados entregues: " + data);
    }
    
    // Cria um pacote ACK
    private static byte[] makeAckPacket(int ackNum) {
        String ackMsg = "ACK:" + ackNum;
        return ackMsg.getBytes(StandardCharsets.UTF_8);
    }

    // Envia um pacote ACK para o roteador
    private static void sendAck(DatagramSocket socket, InetAddress routerAddr, int routerPort, int ackNum) throws IOException {
        byte[] ackData = makeAckPacket(ackNum);
        DatagramPacket ackPacket = new DatagramPacket(ackData, ackData.length, routerAddr, routerPort);
        socket.send(ackPacket);
        System.out.println("[Maquina C] Enviando ACK: " + ackNum);
    }

    public static void main(String[] args) {
        System.out.println("[Maquina C] Destinatario RDT (Go-Back-N) iniciado.");
        
        // Usando DatagramSocket para UDP
        try (DatagramSocket socket = new DatagramSocket()) {
            
            InetAddress routerAddress = InetAddress.getByName(HOST);
            
            // --- Inicialização ---
            // A Máquina C (Destinatário) deve enviar um pacote inicial para que 
            // o roteador (roteador_pc2.py) aprenda seu endereço (IP:PORTA).
            byte[] initData = makeAckPacket(-1); // Pacote de inicialização
            DatagramPacket initPacket = new DatagramPacket(initData, initData.length, routerAddress, PORT);
            socket.send(initPacket);
            System.out.println("[Maquina C] Pacote de inicializacao enviado para o Roteador B em " + HOST + ":" + PORT);

            byte[] receiveBuffer = new byte[BUFFER_SIZE];

            // --- Recepção de dados ---
            while (true) {
                DatagramPacket receivePacket = new DatagramPacket(receiveBuffer, receiveBuffer.length);
                socket.receive(receivePacket); // Bloqueia até receber um pacote

                // Extrai os dados do pacote
                String receivedMessage = new String(receivePacket.getData(), 0, receivePacket.getLength(), StandardCharsets.UTF_8);

                try {
                    String[] parts = receivedMessage.split(":", 3);
                    
                    if (parts.length < 3 || !parts[0].equals("SEQ")) {
                        // Ignora pacotes que não são de dados (ex: INIT_PC1)
                        System.out.println("[Maquina C] Recebeu pacote nao-SEQ (ignorando): " + receivedMessage);
                        continue;
                    }
                    
                    int seqNum = Integer.parseInt(parts[1]);
                    String data = parts[2];
                    
                    System.out.println("\n[Maquina C] Recebeu pacote RDT. Seq: " + seqNum + ", Dados: '" + data + "'");
                    
                    // Lógica do Receptor Go-Back-N
                    if (seqNum == expectedSeqNum) {
                        // --- Pacote correto e na ordem esperada ---
                        System.out.println("[Maquina C] Pacote na ordem esperada. (Esperado: " + expectedSeqNum + " == Recebido: " + seqNum + ")");
                        deliverData(data); // Entrega para a camada superior
                        
                        // Envia ACK para o pacote recebido
                        sendAck(socket, routerAddress, PORT, seqNum);
                        
                        // Atualiza o próximo número de sequência esperado
                        expectedSeqNum = (expectedSeqNum + 1) % SEQ_MODULO;
                        
                    } else {
                        // --- Pacote fora de ordem (duplicado ou adiantado) ---
                        System.out.println("[Maquina C] Pacote fora de ordem (descartado). (Esperado: " + expectedSeqNum + ", Recebido: " + seqNum + ")");
                        
                        // Reenvia ACK para o *último* pacote recebido em ordem
                        // Se expectedSeqNum é 0, o último ACK foi (MODULO - 1)
                        int lastAckNum = (expectedSeqNum == 0) ? (SEQ_MODULO - 1) : (expectedSeqNum - 1);
                        sendAck(socket, routerAddress, PORT, lastAckNum);
                    }
                    
                } catch (NumberFormatException e) {
                    System.out.println("[Maquina C] Erro de formato (possivel corrupcao): " + receivedMessage);
                    // Em caso de corrupção, o receptor GBN não faz nada (espera o timeout do remetente)
                    // Mas, para ajudar o remetente, podemos reenviar o último ACK bom.
                    int lastAckNum = (expectedSeqNum == 0) ? (SEQ_MODULO - 1) : (expectedSeqNum - 1);
                    sendAck(socket, routerAddress, PORT, lastAckNum);
                }
            }

        } catch (SocketException e) {
            System.err.println("[Maquina C] Erro de Socket: " + e.getMessage());
            e.printStackTrace();
        } catch (IOException e) {
            System.err.println("[Maquina C] Erro de I/O: " + e.getMessage());
            e.printStackTrace();
        }

        System.out.println("[Maquina C] Destinatario finalizado.");
    }
}