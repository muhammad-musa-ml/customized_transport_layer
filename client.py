import sys
import getopt
import socket
import random
import threading
from threading import Thread
import queue
import time
import util


class Client:

    def __init__(self, username, dest, port, window_size):
        self.server_addr = dest
        self.server_port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(None)
        self.sock.bind(('', random.randint(10000, 40000)))
        self.name = username
        self.window = window_size
        self.seq_no = random.randrange(0, 1000)
        # to make sequence number
        self.curr_seq = 0
        # to keep track of the ongoing sequnce number
        self.chunk = []
        # list that stores all the chunks
        self.yes = False
        # used to handle quitting
        self.sent = False
        # used to handle quitting as well
        self.sending = queue.Queue()
        # queue that sends packets in window
        self.wind = {}
        # dictionary that has no. of msgs equal to window size
        self.len_chunks = 0
        self.new_msg = False
        # used to tell when a new message is being sent
        self.smth = False
        # bool used to disconnect client incase of too many transmissions
        self.end_msgs = set()
        # to keep track of end messages and their ack resending
        self.end_ack = False
        # to handle the resending of end msgs

    def start(self):
        '''
        Main Loop is here
        Start by sending the server a JOIN message.
        Waits for userinput and then process it
        '''
        # increasing the sequence number by one for a new message
        def seq_gen():
            self.seq_no = self.seq_no+1

        # pre-making the chunks into a list
        def into_chunks(whole_message):
            seq_gen()
            self.sending.queue.clear()
            self.curr_seq = self.seq_no+1

            while len(whole_message) > 0:
                if len(whole_message) > util.CHUNK_SIZE:
                    self.chunk.append(whole_message[:util.CHUNK_SIZE])
                    whole_message = whole_message[util.CHUNK_SIZE:]
                else:
                    self.chunk.append(whole_message)
                    break
            self.len_chunks = len(self.chunk)

            # putting first 3 chunks in queue
            for _ in range(self.window):
                if self.chunk:
                    self.wind[self.curr_seq] = self.chunk[0]
                    pac = util.make_packet("data", self.curr_seq, self.chunk[0])
                    self.sending.put(pac)
                    del self.chunk[0]
                    self.curr_seq += 1
                else:
                    break

        # automatic  joining
        whole_message = util.make_message("join", 1, self.name)
        into_chunks(whole_message)
        packet = util.make_packet("start", self.seq_no,)
        self.new_msg = True
        # handling resending and sending of start msg
        while self.new_msg is True:
            self.sock.sendto(packet.encode("utf-8"), (self.server_addr, self.server_port))
            if self.new_msg is False:
                break
            time.sleep(0.5)

        # while loop to keep running as long as user wants to input commands
        while True:
            whole_message = ""
            # if the quit command has been called,
            # this while loop will start and the function will quit
            if self.yes:
                print("quitting")
                while not self.sent:
                    hell = 1
                    # print('quit loop k andar')
                print('sock close se phele')
                self.yes = False
                self.sock.close()
                print('coket close4 ho gaya hi')
                break
            # this is used to end the function in case of too many retransmisisons
            elif self.smth:
                sys.exit()
                break

            # taking input from client in correct format
            to_send = input("")
            if to_send == "help":
                print('''FORMATS:
Message: msg <number_of_users> <username1> <username2> ... <message>
Available Users: list
File Sharing: file <number_of_users> <username1> <username2> ... <file_name>
Quit: quit \n''')
            else:
                packet = to_send
                if to_send[:3] == "msg":
                    whole_message = util.make_message("send_message", 4, to_send[4:])

                elif to_send[:4] == "file":
                    try:
                        number = int(to_send[5])
                        file_info = to_send[7:].split(" ")
                        file_name = file_info[number]
                        file = open(file_name)
                        data_file = file.read()
                        sending_data = to_send[5:] + " " + data_file
                        whole_message = util.make_message("send_file", 4, sending_data)
                        packet = util.make_packet("start", self.seq_no,)
                    # sends the packet which causes the server
                    # to send unknown command error in case of wrong file message
                    except:
                        whole_message = to_send

                elif to_send == "list":
                    whole_message = util.make_message("request_users_list", 2, to_send)

                elif to_send == "quit":
                    whole_message = util.make_message("disconnect", 1, self.name)
                    into_chunks(whole_message)
                    packet = util.make_packet("start", self.seq_no,)
                    self.new_msg = True
                    self.yes = True
                    while self.new_msg is True:
                        self.sock.sendto(packet.encode("utf-8"),
                                         (self.server_addr, self.server_port))
                        if self.new_msg is False:
                            break
                        time.sleep(0.5)
                    # to make sure packet isn't sent again:
                    continue

                else:
                    print("incorrect userinput format")
                    continue

                # making chunks and sending packet according to input
                into_chunks(whole_message)
                packet = util.make_packet("start", self.seq_no,)
                self.new_msg = True
                while self.new_msg is True:
                    self.sock.sendto(packet.encode("utf-8"), (self.server_addr, self.server_port))
                    if self.new_msg is False:
                        break
                    time.sleep(0.5)

    # handles sending the window and retransmititng the whole window
    # in case of no new ack
    def sender(self):
        while True:
            try:
                # print("im heeere")
                packet = self.sending.get(timeout=0.5)
                # packet = util.make_packet(chunk_to_send)
                self.sock.sendto(packet.encode("utf=8"), (self.server_addr, self.server_port))
            except:
                if self.wind:
                    for number in self.wind.keys():
                        pac = util.make_packet("data", number, self.wind[number])
                        self.sock.sendto(pac.encode("utf-8"),
                                         (self.server_addr, self.server_port))
                # if there is nothing in client_wind, that means this
                # particular conversation is finished and hence the thread is stopped
                else:
                    break

    def receive_handler(self):
        '''
        Waits for a message from server and process it accordingly
        '''
        # one time initialization of local variables
        re_trans = 0
        prev_sno = -1
        fisrt_s_no = 0
        recieved_ack = []
        msg_od = {}

        while True:
            recieved_packet = self.sock.recv(4096)
            recieved_packet_2 = recieved_packet.decode("utf-8")
            print(recieved_packet_2)
            if not util.validate_checksum(recieved_packet_2):
                continue
            type_d, s_no, recieved_message, _ = util.parse_packet(recieved_packet_2)
            # converting s_no into integer
            s_no = int(s_no)

            # checking for how many retransmissions
            # to disconnect if too many of them for the same window
            if s_no != prev_sno:
                prev_sno = s_no
                re_trans = 0
            else:
                re_trans = re_trans + 1
            if re_trans > util.NUM_OF_RETRANSMISSIONS:
                self.smth = True
                self.sock.close()
                sys.exit()

            # handling different kinds of data types
            if type_d == "ack":
                no_to_send = s_no - self.seq_no - 1

                # if ack for end message is sent
                if no_to_send == self.len_chunks:
                    packet = util.make_packet("end", s_no, )
                    self.chunk.clear()
                    self.wind.clear()
                    self.end_ack = True
                    # sending and resending of the end message
                    threading.Thread(target=self.start_resender, args=(packet,)).start()

                # if ack of end message is sent
                if no_to_send > self.len_chunks:
                    self.end_ack = False
                    self.chunk.clear()
                    self.wind.clear()
                    # this will make the function quit
                    if self.yes:
                        self.sent = True
                        break
                    continue

                else:
                    # if new message start a new thread for sending messages
                    if self.new_msg is True:
                        self.new_msg = False
                        threading.Thread(target=self.sender, args=()).start()
                    # handling sliding window
                    count = 0
                    for k in list(self.wind):
                        if k < s_no:
                            del self.wind[k]
                            count += 1
                    for _ in range(count):
                        if self.chunk:
                            self.wind[self.curr_seq] = self.chunk[0]
                            pac = util.make_packet("data", self.curr_seq, self.chunk[0])
                            self.sending.put(pac)
                            del self.chunk[0]
                            self.curr_seq += 1
                        else:
                            continue

            elif type_d == "start":
                fisrt_s_no = s_no+1
                sent_ack = s_no+1
                # last sent ack
                # below variables are renewed everytime a
                # new start message is sent
                msg_od = {}
                # msg_od contains the messages that have been recieved
                msg_od.clear()
                recieved_ack = []
                # contains the acks that have been reccieved
                recieved_ack.clear()
                packet = util.make_packet("ack", fisrt_s_no,)
                self.sock.sendto(packet.encode("utf-8"), (self.server_addr, self.server_port))
                continue

            elif type_d == "data":
                # concatenation
                if s_no not in recieved_ack:
                    msg_od[s_no] = recieved_message
                    recieved_ack.append(s_no)
                    recieved_ack.sort()
                if s_no == sent_ack:
                    sent_ack = recieved_ack[0]+1
                    for idx in range(len(recieved_ack)-1):
                        if recieved_ack[idx] + 1 == recieved_ack[idx+1]:
                            sent_ack = recieved_ack[idx+1]+1
                        else:
                            break
                packet = util.make_packet("ack", sent_ack,)
                self.sock.sendto(packet.encode("utf-8"), (self.server_addr, self.server_port))
                continue

            elif type_d == "end":
                # sending and resending final ack of end
                if s_no in self.end_msgs:
                    packet_ack = util.make_packet("ack", s_no + 1,)
                    self.sock.sendto(packet_ack.encode("utf-8"),
                                     (self.server_addr, self.server_port))
                    continue
                self.end_msgs.add(s_no)

                # concatenating the whole messgae sent
                complete_msg = ""
                packet_ack = util.make_packet("ack", s_no + 1,)
                self.sock.sendto(packet_ack.encode("utf-8"), (self.server_addr, self.server_port))
                for order_no in range(fisrt_s_no, s_no):
                    if order_no in msg_od.keys():
                        complete_msg = complete_msg + msg_od[order_no]
                split_msg = complete_msg.split(" ")

                # handling different messages
                if split_msg[1] == "0":
                    if split_msg[0] == "err_unknown_message":
                        print("disconnected: server received an unknown command")
                    elif split_msg[0] == "err_server_full":
                        print("disconnected: server full")
                    elif split_msg[0] == "err_username_unavailable":
                        print("disconnected: username not available")
                    self.smth = True
                    self.sock.close()
                    sys.exit()
                    break

                elif split_msg[0] == "response_users_list":
                    usernames = " ".join(split_msg[3:])
                    print("list:", usernames.strip())

                elif split_msg[0] == "forward_message":
                    print("msg:", split_msg[3].strip() + ":", " ".join(split_msg[4:]).strip())

                elif split_msg[0] == "forward_file":
                    file_name = self.name + "_" + split_msg[4]
                    file_data = " ".join(split_msg[5:])
                    recv_file = open(file_name, 'w')
                    recv_file.write(file_data)
                    recv_file.close()
                    print("file:", split_msg[3].strip() + ":", split_msg[4].strip())

    # function to handle the sending and restransmissions of "end"
    def start_resender(self, packet):
        while self.end_ack is True:
            self.sock.sendto(packet.encode("utf-8"), (self.server_addr, self.server_port))
            time.sleep(0.5)


# Do not change this part of code
if __name__ == "__main__":
    def helper():
        '''
        This function is just for the sake of our Client module completion
        '''
        print("Client")
        print("-u username | --user=username The username of Client")
        print("-p PORT | --port=PORT The server port, defaults to 15000")
        print("-a ADDRESS | --address=ADDRESS The server ip or hostname, defaults to localhost")
        print("-w WINDOW_SIZE | --window=WINDOW_SIZE The window_size, defaults to 3")
        print("-h | --help Print this help")
    try:
        OPTS, ARGS = getopt.getopt(sys.argv[1:],
                                   "u:p:a:w", ["user=", "port=", "address=", "window="])
    except getopt.error:
        helper()
        exit(1)

    PORT = 15000
    DEST = "localhost"
    USER_NAME = None
    WINDOW_SIZE = 3
    for o, a in OPTS:
        if o in ("-u", "--user="):
            USER_NAME = a
        elif o in ("-p", "--port="):
            PORT = int(a)
        elif o in ("-a", "--address="):
            DEST = a
        elif o in ("-w", "--window="):
            WINDOW_SIZE = a

    if USER_NAME is None:
        print("Missing Username.")
        helper()
        exit(1)

    S = Client(USER_NAME, DEST, PORT, WINDOW_SIZE)
    try:
        # Start receiving Messages
        T = Thread(target=S.receive_handler)
        T.daemon = True
        T.start()
        # Start Client
        S.start()
    except (KeyboardInterrupt, SystemExit):
        sys.exit()
