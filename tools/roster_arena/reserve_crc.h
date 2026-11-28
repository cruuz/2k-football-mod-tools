/* The 352-byte practice-squad overflow block treats its own checksum field as zero. */
static __attribute__((noinline)) unsigned int ROSTER_RESERVE_CRC(const unsigned char *b) {
    unsigned int c=0xffffffffU,i,j;
    for(i=0;i<352;i++) {
        c^=(i>=20 && i<24)?0:b[i];
        for(j=0;j<8;j++) c=(c>>1)^((0U-(c&1))&0xedb88320U);
    }
    return c^0xffffffffU;
}
