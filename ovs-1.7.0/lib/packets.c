/*
 * Copyright (c) 2009, 2010, 2011, 2012 Nicira, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at:
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <config.h>
#include "packets.h"
#include <assert.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdlib.h>
#include "byte-order.h"
#include "csum.h"
#include "flow.h"
#include "dynamic-string.h"
#include "ofpbuf.h"

const struct in6_addr in6addr_exact = IN6ADDR_EXACT_INIT;

/* Parses 's' as a 16-digit hexadecimal number representing a datapath ID.  On
 * success stores the dpid into '*dpidp' and returns true, on failure stores 0
 * into '*dpidp' and returns false.
 *
 * Rejects an all-zeros dpid as invalid. */
bool
dpid_from_string(const char *s, uint64_t *dpidp)
{
    *dpidp = (strlen(s) == 16 && strspn(s, "0123456789abcdefABCDEF") == 16
              ? strtoull(s, NULL, 16)
              : 0);
    return *dpidp != 0;
}

bool
eth_addr_from_string(const char *s, uint8_t ea[ETH_ADDR_LEN])
{
    if (sscanf(s, ETH_ADDR_SCAN_FMT, ETH_ADDR_SCAN_ARGS(ea))
        == ETH_ADDR_SCAN_COUNT) {
        return true;
    } else {
        memset(ea, 0, ETH_ADDR_LEN);
        return false;
    }
}

/* Fills 'b' with an 802.2 SNAP packet with Ethernet source address 'eth_src',
 * the Nicira OUI as SNAP organization and 'snap_type' as SNAP type.  The text
 * string in 'tag' is enclosed as the packet payload.
 *
 * This function is used by Open vSwitch to compose packets in cases where
 * context is important but content doesn't (or shouldn't) matter.  For this
 * purpose, 'snap_type' should be a random number and 'tag' should be an
 * English phrase that explains the purpose of the packet.  (The English phrase
 * gives hapless admins running Wireshark the opportunity to figure out what's
 * going on.) */
void
compose_benign_packet(struct ofpbuf *b, const char *tag, uint16_t snap_type,
                      const uint8_t eth_src[ETH_ADDR_LEN])
{
    size_t tag_size = strlen(tag) + 1;
    char *payload;

    payload = snap_compose(b, eth_addr_broadcast, eth_src, 0x002320, snap_type,
                           tag_size + ETH_ADDR_LEN);
    memcpy(payload, tag, tag_size);
    memcpy(payload + tag_size, eth_src, ETH_ADDR_LEN);
}

/* Insert VLAN header according to given TCI. Packet passed must be Ethernet
 * packet.  Ignores the CFI bit of 'tci' using 0 instead.
 *
 * Also sets 'packet->l2' to point to the new Ethernet header. */
void
eth_push_vlan(struct ofpbuf *packet, ovs_be16 tci)
{
    struct eth_header *eh = packet->data;
    struct vlan_eth_header *veh;

    /* Insert new 802.1Q header. */
    struct vlan_eth_header tmp;
    memcpy(tmp.veth_dst, eh->eth_dst, ETH_ADDR_LEN);
    memcpy(tmp.veth_src, eh->eth_src, ETH_ADDR_LEN);
    tmp.veth_type = htons(ETH_TYPE_VLAN);
    tmp.veth_tci = tci & htons(~VLAN_CFI);
    tmp.veth_next_type = eh->eth_type;

    veh = ofpbuf_push_uninit(packet, VLAN_HEADER_LEN);
    memcpy(veh, &tmp, sizeof tmp);

    packet->l2 = packet->data;
}

/* Removes outermost VLAN header (if any is present) from 'packet'.
 *
 * 'packet->l2' must initially point to 'packet''s Ethernet header. */
void
eth_pop_vlan(struct ofpbuf *packet)
{
    struct vlan_eth_header *veh = packet->l2;
    if (packet->size >= sizeof *veh
        && veh->veth_type == htons(ETH_TYPE_VLAN)) {
        struct eth_header tmp;

        memcpy(tmp.eth_dst, veh->veth_dst, ETH_ADDR_LEN);
        memcpy(tmp.eth_src, veh->veth_src, ETH_ADDR_LEN);
        tmp.eth_type = veh->veth_next_type;

        ofpbuf_pull(packet, VLAN_HEADER_LEN);
        packet->l2 = (char*)packet->l2 + VLAN_HEADER_LEN;
        memcpy(packet->data, &tmp, sizeof tmp);
    }
}

/* Converts hex digits in 'hex' to an Ethernet packet in '*packetp'.  The
 * caller must free '*packetp'.  On success, returns NULL.  On failure, returns
 * an error message and stores NULL in '*packetp'. */
const char *
eth_from_hex(const char *hex, struct ofpbuf **packetp)
{
    struct ofpbuf *packet;

    packet = *packetp = ofpbuf_new(strlen(hex) / 2);

    if (ofpbuf_put_hex(packet, hex, NULL)[0] != '\0') {
        ofpbuf_delete(packet);
        *packetp = NULL;
        return "Trailing garbage in packet data";
    }

    if (packet->size < ETH_HEADER_LEN) {
        ofpbuf_delete(packet);
        *packetp = NULL;
        return "Packet data too short for Ethernet";
    }

    return NULL;
}

/* Given the IP netmask 'netmask', returns the number of bits of the IP address
 * that it specifies, that is, the number of 1-bits in 'netmask'.  'netmask'
 * must be a CIDR netmask (see ip_is_cidr()). */
int
ip_count_cidr_bits(ovs_be32 netmask)
{
    assert(ip_is_cidr(netmask));
    return 32 - ctz(ntohl(netmask));
}

void
ip_format_masked(ovs_be32 ip, ovs_be32 mask, struct ds *s)
{
    ds_put_format(s, IP_FMT, IP_ARGS(&ip));
    if (mask != htonl(UINT32_MAX)) {
        if (ip_is_cidr(mask)) {
            ds_put_format(s, "/%d", ip_count_cidr_bits(mask));
        } else {
            ds_put_format(s, "/"IP_FMT, IP_ARGS(&mask));
        }
    }
}


/* Stores the string representation of the IPv6 address 'addr' into the
 * character array 'addr_str', which must be at least INET6_ADDRSTRLEN
 * bytes long. */
void
format_ipv6_addr(char *addr_str, const struct in6_addr *addr)
{
    inet_ntop(AF_INET6, addr, addr_str, INET6_ADDRSTRLEN);
}

void
print_ipv6_addr(struct ds *string, const struct in6_addr *addr)
{
    char *dst;

    ds_reserve(string, string->length + INET6_ADDRSTRLEN);

    dst = string->string + string->length;
    format_ipv6_addr(dst, addr);
    string->length += strlen(dst);
}

void
print_ipv6_masked(struct ds *s, const struct in6_addr *addr,
                  const struct in6_addr *mask)
{
    print_ipv6_addr(s, addr);
    if (mask && !ipv6_mask_is_exact(mask)) {
        if (ipv6_is_cidr(mask)) {
            int cidr_bits = ipv6_count_cidr_bits(mask);
            ds_put_format(s, "/%d", cidr_bits);
        } else {
            ds_put_char(s, '/');
            print_ipv6_addr(s, mask);
        }
    }
}

struct in6_addr ipv6_addr_bitand(const struct in6_addr *a,
                                 const struct in6_addr *b)
{
    int i;
    struct in6_addr dst;

#ifdef s6_addr32
    for (i=0; i<4; i++) {
        dst.s6_addr32[i] = a->s6_addr32[i] & b->s6_addr32[i];
    }
#else
    for (i=0; i<16; i++) {
        dst.s6_addr[i] = a->s6_addr[i] & b->s6_addr[i];
    }
#endif

    return dst;
}

/* Returns an in6_addr consisting of 'mask' high-order 1-bits and 128-N
 * low-order 0-bits. */
struct in6_addr
ipv6_create_mask(int mask)
{
    struct in6_addr netmask;
    uint8_t *netmaskp = &netmask.s6_addr[0];

    memset(&netmask, 0, sizeof netmask);
    while (mask > 8) {
        *netmaskp = 0xff;
        netmaskp++;
        mask -= 8;
    }

    if (mask) {
        *netmaskp = 0xff << (8 - mask);
    }

    return netmask;
}

/* Given the IPv6 netmask 'netmask', returns the number of bits of the IPv6
 * address that it specifies, that is, the number of 1-bits in 'netmask'.
 * 'netmask' must be a CIDR netmask (see ipv6_is_cidr()). */
int
ipv6_count_cidr_bits(const struct in6_addr *netmask)
{
    int i;
    int count = 0;
    const uint8_t *netmaskp = &netmask->s6_addr[0];

    assert(ipv6_is_cidr(netmask));

    for (i=0; i<16; i++) {
        if (netmaskp[i] == 0xff) {
            count += 8;
        } else {
            uint8_t nm;

            for(nm = netmaskp[i]; nm; nm <<= 1) {
                count++;
            }
            break;
        }

    }

    return count;
}

/* Returns true if 'netmask' is a CIDR netmask, that is, if it consists of N
 * high-order 1-bits and 128-N low-order 0-bits. */
bool
ipv6_is_cidr(const struct in6_addr *netmask)
{
    const uint8_t *netmaskp = &netmask->s6_addr[0];
    int i;

    for (i=0; i<16; i++) {
        if (netmaskp[i] != 0xff) {
            uint8_t x = ~netmaskp[i];
            if (x & (x + 1)) {
                return false;
            }
            while (++i < 16) {
                if (netmaskp[i]) {
                    return false;
                }
            }
        }
    }

    return true;
}

/* Populates 'b' with an Ethernet II packet headed with the given 'eth_dst',
 * 'eth_src' and 'eth_type' parameters.  A payload of 'size' bytes is allocated
 * in 'b' and returned.  This payload may be populated with appropriate
 * information by the caller.  Sets 'b''s 'l2' and 'l3' pointers to the
 * Ethernet header and payload respectively.
 *
 * The returned packet has enough headroom to insert an 802.1Q VLAN header if
 * desired. */
void *
eth_compose(struct ofpbuf *b, const uint8_t eth_dst[ETH_ADDR_LEN],
            const uint8_t eth_src[ETH_ADDR_LEN], uint16_t eth_type,
            size_t size)
{
    void *data;
    struct eth_header *eth;

    ofpbuf_clear(b);

    ofpbuf_prealloc_tailroom(b, ETH_HEADER_LEN + VLAN_HEADER_LEN + size);
    ofpbuf_reserve(b, VLAN_HEADER_LEN);
    eth = ofpbuf_put_uninit(b, ETH_HEADER_LEN);
    data = ofpbuf_put_uninit(b, size);

    memcpy(eth->eth_dst, eth_dst, ETH_ADDR_LEN);
    memcpy(eth->eth_src, eth_src, ETH_ADDR_LEN);
    eth->eth_type = htons(eth_type);

    b->l2 = eth;
    b->l3 = data;

    return data;
}

/* Populates 'b' with an Ethernet LLC+SNAP packet headed with the given
 * 'eth_dst', 'eth_src', 'snap_org', and 'snap_type'.  A payload of 'size'
 * bytes is allocated in 'b' and returned.  This payload may be populated with
 * appropriate information by the caller.
 *
 * The returned packet has enough headroom to insert an 802.1Q VLAN header if
 * desired. */
void *
snap_compose(struct ofpbuf *b, const uint8_t eth_dst[ETH_ADDR_LEN],
             const uint8_t eth_src[ETH_ADDR_LEN],
             unsigned int oui, uint16_t snap_type, size_t size)
{
    struct eth_header *eth;
    struct llc_snap_header *llc_snap;
    void *payload;

    /* Compose basic packet structure.  (We need the payload size to stick into
     * the 802.2 header.) */
    ofpbuf_clear(b);
    ofpbuf_prealloc_tailroom(b, ETH_HEADER_LEN + VLAN_HEADER_LEN
                             + LLC_SNAP_HEADER_LEN + size);
    ofpbuf_reserve(b, VLAN_HEADER_LEN);
    eth = ofpbuf_put_zeros(b, ETH_HEADER_LEN);
    llc_snap = ofpbuf_put_zeros(b, LLC_SNAP_HEADER_LEN);
    payload = ofpbuf_put_uninit(b, size);

    /* Compose 802.2 header. */
    memcpy(eth->eth_dst, eth_dst, ETH_ADDR_LEN);
    memcpy(eth->eth_src, eth_src, ETH_ADDR_LEN);
    eth->eth_type = htons(b->size - ETH_HEADER_LEN);

    /* Compose LLC, SNAP headers. */
    llc_snap->llc.llc_dsap = LLC_DSAP_SNAP;
    llc_snap->llc.llc_ssap = LLC_SSAP_SNAP;
    llc_snap->llc.llc_cntl = LLC_CNTL_SNAP;
    llc_snap->snap.snap_org[0] = oui >> 16;
    llc_snap->snap.snap_org[1] = oui >> 8;
    llc_snap->snap.snap_org[2] = oui;
    llc_snap->snap.snap_type = htons(snap_type);

    return payload;
}

static void
packet_set_ipv4_addr(struct ofpbuf *packet, ovs_be32 *addr, ovs_be32 new_addr)
{
    struct ip_header *nh = packet->l3;

    if (nh->ip_proto == IPPROTO_TCP && packet->l7) {
        struct tcp_header *th = packet->l4;

        th->tcp_csum = recalc_csum32(th->tcp_csum, *addr, new_addr);
    } else if (nh->ip_proto == IPPROTO_UDP && packet->l7) {
        struct udp_header *uh = packet->l4;

        if (uh->udp_csum) {
            uh->udp_csum = recalc_csum32(uh->udp_csum, *addr, new_addr);
            if (!uh->udp_csum) {
                uh->udp_csum = htons(0xffff);
            }
        }
    }
    nh->ip_csum = recalc_csum32(nh->ip_csum, *addr, new_addr);
    *addr = new_addr;
}

/* Modifies the IPv4 header fields of 'packet' to be consistent with 'src',
 * 'dst', 'tos', and 'ttl'.  Updates 'packet''s L4 checksums as appropriate.
 * 'packet' must contain a valid IPv4 packet with correctly populated l[347]
 * markers. */
void
packet_set_ipv4(struct ofpbuf *packet, ovs_be32 src, ovs_be32 dst,
                uint8_t tos, uint8_t ttl)
{
    struct ip_header *nh = packet->l3;

    if (nh->ip_src != src) {
        packet_set_ipv4_addr(packet, &nh->ip_src, src);
    }

    if (nh->ip_dst != dst) {
        packet_set_ipv4_addr(packet, &nh->ip_dst, dst);
    }

    if (nh->ip_tos != tos) {
        uint8_t *field = &nh->ip_tos;

        nh->ip_csum = recalc_csum16(nh->ip_csum, htons((uint16_t) *field),
                                    htons((uint16_t) tos));
        *field = tos;
    }

    if (nh->ip_ttl != ttl) {
        uint8_t *field = &nh->ip_ttl;

        nh->ip_csum = recalc_csum16(nh->ip_csum, htons(*field << 8),
                                    htons(ttl << 8));
        *field = ttl;
    }
}

static void
packet_set_port(ovs_be16 *port, ovs_be16 new_port, ovs_be16 *csum)
{
    if (*port != new_port) {
        *csum = recalc_csum16(*csum, *port, new_port);
        *port = new_port;
    }
}

/* Sets the TCP source and destination port ('src' and 'dst' respectively) of
 * the TCP header contained in 'packet'.  'packet' must be a valid TCP packet
 * with its l4 marker properly populated. */
void
packet_set_tcp_port(struct ofpbuf *packet, ovs_be16 src, ovs_be16 dst)
{
    struct tcp_header *th = packet->l4;

    packet_set_port(&th->tcp_src, src, &th->tcp_csum);
    packet_set_port(&th->tcp_dst, dst, &th->tcp_csum);
}

/* Sets the UDP source and destination port ('src' and 'dst' respectively) of
 * the UDP header contained in 'packet'.  'packet' must be a valid UDP packet
 * with its l4 marker properly populated. */
void
packet_set_udp_port(struct ofpbuf *packet, ovs_be16 src, ovs_be16 dst)
{
    struct udp_header *uh = packet->l4;

    if (uh->udp_csum) {
        packet_set_port(&uh->udp_src, src, &uh->udp_csum);
        packet_set_port(&uh->udp_dst, dst, &uh->udp_csum);

        if (!uh->udp_csum) {
            uh->udp_csum = htons(0xffff);
        }
    } else {
        uh->udp_src = src;
        uh->udp_dst = dst;
    }
}

/* If 'packet' is a TCP packet, returns the TCP flags.  Otherwise, returns 0.
 *
 * 'flow' must be the flow corresponding to 'packet' and 'packet''s header
 * pointers must be properly initialized (e.g. with flow_extract()). */
uint8_t
packet_get_tcp_flags(const struct ofpbuf *packet, const struct flow *flow)
{
    if ((flow->dl_type == htons(ETH_TYPE_IP) ||
         flow->dl_type == htons(ETH_TYPE_IPV6)) &&
        flow->nw_proto == IPPROTO_TCP && packet->l7) {
        const struct tcp_header *tcp = packet->l4;
        return TCP_FLAGS(tcp->tcp_ctl);
    } else {
        return 0;
    }
}

/* Appends a string representation of the TCP flags value 'tcp_flags'
 * (e.g. obtained via packet_get_tcp_flags() or TCP_FLAGS) to 's', in the
 * format used by tcpdump. */
void
packet_format_tcp_flags(struct ds *s, uint8_t tcp_flags)
{
    if (!tcp_flags) {
        ds_put_cstr(s, "none");
        return;
    }

    if (tcp_flags & TCP_SYN) {
        ds_put_char(s, 'S');
    }
    if (tcp_flags & TCP_FIN) {
        ds_put_char(s, 'F');
    }
    if (tcp_flags & TCP_PSH) {
        ds_put_char(s, 'P');
    }
    if (tcp_flags & TCP_RST) {
        ds_put_char(s, 'R');
    }
    if (tcp_flags & TCP_URG) {
        ds_put_char(s, 'U');
    }
    if (tcp_flags & TCP_ACK) {
        ds_put_char(s, '.');
    }
    if (tcp_flags & 0x40) {
        ds_put_cstr(s, "[40]");
    }
    if (tcp_flags & 0x80) {
        ds_put_cstr(s, "[80]");
    }
}
