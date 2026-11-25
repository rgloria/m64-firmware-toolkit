/* TEXT_ORG is passed with --defsym by build.py (= first 4-aligned address after the base image). */
MEMORY
{
  FLASH (rx) : ORIGIN = TEXT_ORG, LENGTH = 0x08100000 - TEXT_ORG
  RAM   (rw) : ORIGIN = 0x240F0000, LENGTH = 0x8000     /* unused tail of AXI SRAM, see LIBRARY_CHANGES.md */
}
SECTIONS
{
  .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
  .data : { *(.data*) } > RAM AT > FLASH
  .bss (NOLOAD) : { __bss_start__ = .; *(.bss*) *(COMMON) . = ALIGN(4); __bss_end__ = .; } > RAM
  ASSERT(SIZEOF(.data) == 0, "initialised data is not supported: make it const or zero")
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) }
}
