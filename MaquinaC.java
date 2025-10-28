import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class MaquinaC {
    private static final String HOST = "127.0.0.1";
    private static final int PORT = 55555;
    private static final int BUFFER_SIZE = 4096;
    private static final int WINDOW_SIZE = 5; // Janela de recepção
    private static final int SEQ_MODULO = 10; // Espaço de num de sequência (deve ser >= 2 * WINDOW_SIZE)
    
    private static int rcv_base = 0; // Base da janela de recepção
    private static Map<Integer, String> ooo_buffer = new HashMap<>(); // Buffer para pacotes fora de ordem (Out-Of-Order)
    
    // Camada de aplicação
    private static void deliverData(String data) {
        System.out.println("-> [CAMADA SUPERIOR] Dados entregues: " + data);
    }
    
    // Cria um pacote ACK no formato esperado por Janela.py
    private static byte[] makeAckPacket(int ackNum) {
        int seq = -1; // -1 para indicar que não é um pacote de dados
        int flag_ack = 1; // Flag 1 para indicar que é um ACK

        // Monta o cabeçalho de 12 bytes: 4 (seq) + 4 (ack) + 4 (flag)
        byte[] header = new byte[12];
        
        // Seq
        header[0] = (byte)(seq >> 24);
        header[1] = (byte)(seq >> 16);
        header[2] = (byte)(seq >> 8);
        header[3] = (byte)(seq);

        // Ack
        header[4] = (byte)(ackNum >> 24);
        header[5] = (byte)(ackNum >> 16);
        header[6] = (byte)(ackNum >> 8);
        header[7] = (byte)(ackNum);

        // Flag
        int bits_flag = (flag_ack & 1) << 31;
        header[8] = (byte)(bits_flag >> 24);
        header[9] = (byte)(bits_flag >> 16);
        header[10] = (byte)(bits_flag >> 8);
        header[11] = (byte)(bits_flag);

        return header;
    }

    // Envia um pacote ACK para o roteador
    private static void sendAck(DatagramSocket socket, InetAddress routerAddr, int routerPort, int ackNum) throws IOException {
        byte[] ackData = makeAckPacket(ackNum);
        DatagramPacket ackPacket = new DatagramPacket(ackData, ackData.length, routerAddr, routerPort);
        socket.send(ackPacket);
        System.out.println("[Maquina C] Enviando ACK para o pacote: " + ackNum);
    }

    // Verifica se um número de sequência está na janela de recepção
    private static boolean isInWindow(int seqNum) {
        int end = (rcv_base + WINDOW_SIZE) % SEQ_MODULO;
        if (rcv_base < end) { // Janela não dá a volta
            return seqNum >= rcv_base && seqNum < end;
        } else { // Janela dá a volta (ex: base=8, fim=3, janela={8,9,0,1,2})
            return seqNum >= rcv_base || seqNum < end;
        }
    }

    public static void main(String[] args) {
        System.out.println("[Maquina C] Destinatario RDT (Selective Repeat) iniciado.");
        
        try (DatagramSocket socket = new DatagramSocket()) {
            
            InetAddress routerAddress = InetAddress.getByName(HOST);
            
            // Envia um pacote inicial para o roteador aprender seu endereço
            byte[] initData = "INIT_PC2".getBytes(StandardCharsets.UTF_8);
            DatagramPacket initPacket = new DatagramPacket(initData, initData.length, routerAddress, PORT);
            socket.send(initPacket);
            System.out.println("[Maquina C] Pacote de inicializacao enviado para o Roteador B.");

            byte[] buffer = new byte[BUFFER_SIZE];

            while (true) {
                DatagramPacket receivePacket = new DatagramPacket(buffer, buffer.length);
                socket.receive(receivePacket);

                byte[] receivedData = receivePacket.getData();
                int length = receivePacket.getLength();

                if (length < 12) {
                    System.out.println("[Maquina C] Recebeu pacote muito curto (ignorando): " + new String(receivedData, 0, length));
                    continue;
                }

                // Lendo o cabeçalho manualmente (bytes_para_int em Java)
                long seqNum_long = 0;
                for(int i=0; i<4; i++) seqNum_long = (seqNum_long << 8) | (receivedData[i] & 0xFF);
                int seqNum = (int) seqNum_long;

                String data = new String(receivedData, 12, length - 12, StandardCharsets.UTF_8);
                
                System.out.println("\n[Maquina C] Recebeu pacote. Seq: " + seqNum + ", Dados: '" + data + "'");
                
                // Lógica do Receptor Selective Repeat
                if (isInWindow(seqNum)) {
                    // Pacote está dentro da janela, envia ACK para ele
                    sendAck(socket, routerAddress, PORT, seqNum);

                    if (seqNum == rcv_base) {
                        // Pacote esperado, entrega para a camada superior
                        deliverData(data);
                        
                        // Avança a base da janela e entrega pacotes do buffer que se tornaram contíguos
                        rcv_base = (rcv_base + 1) % SEQ_MODULO;
                        while (ooo_buffer.containsKey(rcv_base)) {
                            String bufferedData = ooo_buffer.remove(rcv_base);
                            deliverData(bufferedData);
                            System.out.println("[Maquina C] Entregou pacote " + rcv_base + " do buffer.");
                            rcv_base = (rcv_base + 1) % SEQ_MODULO;
                        }
                        System.out.println("[Maquina C] Janela avançou. Nova base: " + rcv_base);

                    } else {
                        // Pacote fora de ordem, mas na janela. Armazena no buffer se ainda não estiver lá.
                        if (!ooo_buffer.containsKey(seqNum)) {
                            ooo_buffer.put(seqNum, data);
                            System.out.println("[Maquina C] Pacote " + seqNum + " fora de ordem, armazenado no buffer.");
                        }
                    }
                } else {
                     // Verifica se é um pacote antigo que já foi confirmado (está na janela anterior)
                    int prev_window_base = (rcv_base - WINDOW_SIZE + SEQ_MODULO) % SEQ_MODULO;
                    boolean is_old_ack;
                    if (prev_window_base < rcv_base) {
                        is_old_ack = seqNum >= prev_window_base && seqNum < rcv_base;
                    } else {
                        is_old_ack = seqNum >= prev_window_base || seqNum < rcv_base;
                    }

                    if(is_old_ack) {
                        // Pacote já foi recebido e entregue. O ACK pode ter se perdido. Reenvia o ACK para ele.
                        System.out.println("[Maquina C] Recebeu pacote antigo (Seq: " + seqNum + "). Reenviando ACK.");
                        sendAck(socket, routerAddress, PORT, seqNum);
                    } else {
                        // Pacote muito adiantado (fora da janela), descarta
                        System.out.println("[Maquina C] Pacote fora da janela (descartado). (Base: " + rcv_base + ", Recebido: " + seqNum + ")");
                    }
                }
            }

        } catch (IOException e) {
            System.err.println("[Maquina C] Erro de I/O: " + e.getMessage());
            e.printStackTrace();
        }

        System.out.println("[Maquina C] Destinatario finalizado.");
    }
}