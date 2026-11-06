SECTIONS {
  .site_a 0x0014E8B0 : { *(.site_a) }
  .site_b 0x0014E930 : { *(.site_b) }
  .site_c 0x0014E9D0 : { *(.site_c) }
  .site_d 0x0014EFE0 : { *(.site_d) }
  .site_e 0x0014F16F : { *(.site_e) }
  .site_f 0x0014F249 : { *(.site_f) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.text) *(.data) *(.bss) }
}
ASSERT(SIZEOF(.site_a) <= 0x80, "site A overflows 0x14E8B0..0x14E92F")
ASSERT(SIZEOF(.site_b) <= 0xA0, "site B overflows 0x14E930..0x14E9CF")
ASSERT(SIZEOF(.site_c) <= 0x1F0, "site C overflows 0x14E9D0..0x14EBBF")
ASSERT(SIZEOF(.site_d) <= 0x188, "site D overflows 0x14EFE0..0x14F167")
ASSERT(SIZEOF(.site_e) == 1, "site E is one ret")
ASSERT(SIZEOF(.site_f) <= 0x6E, "site F overflows 0x14F249..0x14F2B6")
