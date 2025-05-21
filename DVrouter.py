####################################################
# DVrouter.py
# Name: Nguyễn Hữu Hồng Phúc
# HUID:
#####################################################

from router import Router
from packet import Packet
import json
import copy

MAXIMUM = float('inf')

class DVrouter(Router):
    """Distance vector routing protocol implementation.

    Add your own class fields and initialization code (e.g. to create forwarding table
    data structures). See the `Router` base class for docstrings of the methods to
    override.
    """

    def __init__(self, addr, heartbeat_time):
        # Call base class initializer
        super().__init__(addr)
        self.addr = addr
        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        self.neighbors = {}        # port -> (neighbor address, cost)
        self.dv = {addr: (0, addr)}  # destination -> (cost, next_hop)
        self.neighbor_dvs = {}     # neighbor address -> {destination: cost}
        self.forwarding_table = {} # destination -> port

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        # TODO
        if packet.is_traceroute:
            # Forward traceroute packets using the forwarding table
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst]
                self.send(out_port, packet)
        else:
            # Handle routing update packets
            try:
                received_dv = json.loads(packet.content)
            except:
                return  # Ignore malformed packet

            src = packet.src_addr
            self.neighbor_dvs[src] = received_dv  # Save neighbor's DV

            changed = self._recompute_dv()  # Run Bellman-Ford

            if changed:
                self._update_forwarding_table()
                self._broadcast_dv()

    def handle_new_link(self, port, endpoint, cost):
        # Save new neighbor link
        self.neighbors[port] = (endpoint, cost)

        # Update DV if this link offers a better direct route
        if endpoint not in self.dv or cost < self.dv[endpoint][0]:
            self.dv[endpoint] = (cost, endpoint)

        # Make sure neighbor has an entry in neighbor_dvs
        if endpoint not in self.neighbor_dvs:
            self.neighbor_dvs[endpoint] = {}

        # Recompute routing info
        changed = self._recompute_dv()
        if changed:
            self._update_forwarding_table()
            self._broadcast_dv()

    def handle_remove_link(self, port):
        if port in self.neighbors:
            neighbor_addr, _ = self.neighbors[port]

            # Remove neighbor and their DV
            del self.neighbors[port]
            if neighbor_addr in self.neighbor_dvs:
                del self.neighbor_dvs[neighbor_addr]

            # Recompute based on new topology
            changed = self._recompute_dv()
            if changed:
                self._update_forwarding_table()
                self._broadcast_dv()

    def handle_time(self, time_ms):
        # Periodically send our distance vector
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast_dv()

    def _broadcast_dv(self):
        # Prepare and send our current distance vector to all neighbors
        dv_to_send = {}
        for dest in self.dv:
            cost, _ = self.dv[dest]
            dv_to_send[dest] = cost

        content = json.dumps(dv_to_send)

        for port in self.neighbors:
            neighbor_addr, _ = self.neighbors[port]
            pkt = Packet(Packet.ROUTING, self.addr, neighbor_addr, content)
            self.send(port, pkt)

    def _recompute_dv(self):
        # Recalculate the best routes using Bellman-Ford
        old_dv = copy.deepcopy(self.dv)
        new_dv = {self.addr: (0, self.addr)}

        destinations = set()
        destinations.update(self.dv.keys())
        for dv in self.neighbor_dvs.values():
            for dest in dv:
                destinations.add(dest)

        for dest in destinations:
            if dest == self.addr:
                continue

            best_cost = MAXIMUM
            best_next = None

            for port in self.neighbors:
                neighbor_addr, link_cost = self.neighbors[port]

                # Direct neighbor route
                if neighbor_addr == dest:
                    if link_cost < best_cost:
                        best_cost = link_cost
                        best_next = neighbor_addr
                # Route via neighbor
                elif neighbor_addr in self.neighbor_dvs:
                    neighbor_dv = self.neighbor_dvs[neighbor_addr]
                    if dest in neighbor_dv:
                        total = link_cost + neighbor_dv[dest]
                        if total < best_cost:
                            best_cost = total
                            best_next = neighbor_addr

            # Save best route found
            if best_cost < MAXIMUM:
                new_dv[dest] = (best_cost, best_next)

        changed = (new_dv != self.dv)
        self.dv = new_dv
        return changed

    def _update_forwarding_table(self):
        # Update next-hop ports based on the current DV
        self.forwarding_table = {}

        for dest in self.dv:
            if dest == self.addr:
                continue
            cost, next_hop = self.dv[dest]

            for port in self.neighbors:
                neighbor_addr, _ = self.neighbors[port]
                if neighbor_addr == next_hop:
                    self.forwarding_table[dest] = port
                    break

    def __repr__(self):
        # Print debug information for the router
        lines = []
        lines.append("DVrouter(addr=" + self.addr + ")")

        lines.append("\nDistance Vector:")
        for dest in sorted(self.dv):
            cost, nhop = self.dv[dest]
            lines.append("  Dest: " + dest + ", Cost: " + str(cost) + ", Next Hop: " + nhop)

        lines.append("\nForwarding Table:")
        for dest in sorted(self.forwarding_table):
            port = self.forwarding_table[dest]
            lines.append("  Dest: " + dest + ", Out Port: " + str(port))

        lines.append("\nNeighbors:")
        for port in self.neighbors:
            addr, cost = self.neighbors[port]
            lines.append("  Port: " + str(port) + ", Addr: " + addr + ", Cost: " + str(cost))

        return "\n".join(lines)
