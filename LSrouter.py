from router import Router
from packet import Packet
import json
import heapq

class LSrouter(Router):
    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)
        self.addr = addr
        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        self.topology = {}  # node -> {neighbor: cost}
        self.sequence_numbers = {}  # node -> latest seq num seen
        self.forwarding_table = {}  # dest -> port
        self.seq_num = 0

        self.neighbor_info = {}  # port -> (neighbor, cost)
        self.port_to_neighbor = {}  # port -> neighbor
        self.neighbor_to_port = {}  # neighbor -> port

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                self.send(self.forwarding_table[dst], packet)
            return

        try:
            content = json.loads(packet.content)
        except:
            return  # Ignore malformed packet

        origin = packet.src_addr
        seq = content['seq']
        links = content['links']

        if origin in self.sequence_numbers and seq <= self.sequence_numbers[origin]:
            return  # Old or duplicate

        self.sequence_numbers[origin] = seq
        self.topology[origin] = links

        # Flood LSP to all neighbors except the one it came from
        for p in self.port_to_neighbor:
            if p != port:
                neighbor = self.port_to_neighbor[p]
                pkt = Packet(Packet.ROUTING, origin, neighbor, packet.content)
                self.send(p, pkt)

        self._recompute_routes()

    def handle_new_link(self, port, endpoint, cost):
        # Update port-neighbor mapping
        self.neighbor_info[port] = (endpoint, cost)
        self.port_to_neighbor[port] = endpoint
        self.neighbor_to_port[endpoint] = port

        # Update topology
        if self.addr not in self.topology:
            self.topology[self.addr] = {}
        self.topology[self.addr][endpoint] = cost

        self._broadcast_lsp()
        self._recompute_routes()

    def handle_remove_link(self, port):
        if port not in self.neighbor_info:
            return

        neighbor, _ = self.neighbor_info[port]

        # Remove from internal tracking
        del self.neighbor_info[port]
        del self.port_to_neighbor[port]
        del self.neighbor_to_port[neighbor]

        if self.addr in self.topology and neighbor in self.topology[self.addr]:
            del self.topology[self.addr][neighbor]

        self._broadcast_lsp()
        self._recompute_routes()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast_lsp()

    def _broadcast_lsp(self):
        self.seq_num += 1
        links = {neighbor: cost for neighbor, cost in self.topology.get(self.addr, {}).items()}

        content = json.dumps({
            "seq": self.seq_num,
            "links": links
        })

        for port in self.port_to_neighbor:
            neighbor = self.port_to_neighbor[port]
            pkt = Packet(Packet.ROUTING, self.addr, neighbor, content)
            self.send(port, pkt)

    def _recompute_routes(self):
        dist = {self.addr: 0}
        prev = {}
        visited = set()
        heap = [(0, self.addr)]

        while heap:
            cost, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)

            for neighbor, weight in self.topology.get(node, {}).items():
                if neighbor not in dist or cost + weight < dist[neighbor]:
                    dist[neighbor] = cost + weight
                    prev[neighbor] = node
                    heapq.heappush(heap, (dist[neighbor], neighbor))

        self.forwarding_table = {}
        for dest in dist:
            if dest == self.addr:
                continue

            # Backtrack to find next hop
            next_hop = dest
            while prev.get(next_hop) != self.addr:
                next_hop = prev[next_hop]

            if next_hop in self.neighbor_to_port:
                self.forwarding_table[dest] = self.neighbor_to_port[next_hop]

    def __repr__(self):
        lines = [f"LSrouter(addr={self.addr})"]
        lines.append("\nForwarding Table:")
        for dest in sorted(self.forwarding_table):
            port = self.forwarding_table[dest]
            lines.append(f"  Dest: {dest}, Port: {port}")
        lines.append("\nTopology:")
        for node in sorted(self.topology):
            for neighbor, cost in self.topology[node].items():
                lines.append(f"  {node} --({cost})--> {neighbor}")
        return "\n".join(lines)
