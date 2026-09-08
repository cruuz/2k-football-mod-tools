/* M3 capacity experiment, NOT installed by build_runtime or the mode owner.
 * Appended to runtime.c only by measure_m3.py. This measures a concrete
 * purchase transaction before its native UI and the remaining M3 features.
 * The transient quote uses 3328..3367, after the controller-visit array.
 * No new allocation, native progression hook, or attribute table is added.
 */
static u32 upgrade_cost(u32 value) {
    return value<70?10:value<80?15:value<90?25:value<95?40:value<99?60:0;
}
static u32 upgrade_field(u32 field) {
    return field>=0x36 && field<=0x51 && field!=0x4b && field!=0x4d && field!=0x4f;
}
u32 FC m3_upgrade_quote(u32 manager,u32 field) {
    u8 *p; u32 value,cost;
    S(3328)=0;
    if(!hub(manager) || !upgrade_field(field) || !(p=(u8 *)primary())) return 0;
    value=p[field]; cost=upgrade_cost(value);
    if(!cost || S(64)<cost) return 0;
    S(3332)=field; S(3336)=value; S(3340)=S(64);
    S(3344)=S(28); move_bytes(state+3348,state+40,16);
    S(3364)=manager;
    S(3328)=(u32)p;
    return cost;
}
u32 FC m3_upgrade_commit(u32 manager,u32 answer) {
    u8 *p=(u8 *)S(3328); u32 field=S(3332),value=S(3336),cost=upgrade_cost(value),i;
    S(3328)=0; /* cancel, stale confirmation and replay all consume the quote */
    if(answer!=1 || manager!=S(3364) || !hub(manager) || !p ||
       primary()!=(u32)p || S(28)!=S(3344) || !upgrade_field(field) ||
       p[field]!=value || !cost || S(64)!=S(3340) || S(64)<cost) return 0;
    for(i=0;i<16;i++) if(state[40+i]!=state[3348+i]) return 0;
    p[field]=(u8)(value+1); S(64)-=cost;
    return 1;
}
