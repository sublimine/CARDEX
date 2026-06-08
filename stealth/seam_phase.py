#!/usr/bin/env python3
"""Seam phase for the T1 sweep: for each portal with harvested records, write to
vehicle_index (BEFORE/AFTER), capture 5 sample rows, then PURGE (validate-only).
No browser here (runs after sweep closes it). Emits the final T1 marker table."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

STEALTH = Path(__file__).resolve().parent
DUMPS = STEALTH / "evidence" / "dumps"
SWEEP = STEALTH / "evidence" / "sweep"
MARKER = SWEEP / "t1_marker.json"

def psql(sql):
    p=subprocess.run(["docker","exec","cardex-pg","psql","-U","cardex","-d","cardex","-t","-A","-c",sql],
                     capture_output=True,text=True,encoding="utf-8",errors="replace")
    return p.stdout.strip()

def main():
    marker=json.loads(MARKER.read_text(encoding="utf-8"))
    out=[]
    for domain,r in marker.items():
        row={"domain":domain,"verdict":r["verdict"],"records_harvested":r["records"],
             "before":None,"after":None,"samples":[],"status":None}
        jf=DUMPS/f"{domain}_harvest.jsonl"
        if r["verdict"]=="OK" and r["records"]>0 and jf.exists():
            before=psql(f"SELECT count(*) FROM vehicle_index WHERE source_domain='{domain}';")
            row["before"]=before
            rc=subprocess.run([sys.executable,str(STEALTH/"seam_writer.py"),"--records",str(jf),
                               "--source",domain,"--country",r["country"]],
                              capture_output=True,text=True,encoding="utf-8",errors="replace")
            after=psql(f"SELECT count(*) FROM vehicle_index WHERE source_domain='{domain}';")
            row["after"]=after
            samp=psql(f"SELECT COALESCE(titulo_modelo,'(no title)')||' | '||COALESCE(precio::text,'-')||' | '||COALESCE(anio::text,'-') FROM vehicle_index WHERE source_domain='{domain}' ORDER BY created_at DESC LIMIT 5;")
            row["samples"]=[s for s in samp.split("\n") if s]
            # PURGE (validate-with-limit-and-purge)
            psql(f"DELETE FROM vehicle_index WHERE source_domain='{domain}' AND sitemap_source='stealth';")
            row["status"]="HARVESTED" if int(after or 0)>int(before or 0) else "NO_DELTA"
        else:
            row["status"]="REQUIRES_PROXY" if r["verdict"] in ("BLOCKED","ERROR") else "NO_LISTINGS_SSR"
        out.append(row)
        print(f"[{domain}] {row['status']} before={row['before']} after={row['after']} harvested={row['records_harvested']}",flush=True)
    (SWEEP/"t1_final.json").write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    # marker table
    print("\n================ T1 SWEEP MARKER ================",flush=True)
    print(f"{'PORTAL':<24}{'STATUS':<16}{'AFTER':>7}  SAMPLE",flush=True)
    for r in out:
        icon={"HARVESTED":"OK","REQUIRES_PROXY":"PROXY","NO_LISTINGS_SSR":"NO-SSR","NO_DELTA":"NODELTA"}.get(r["status"],"?")
        s=(r["samples"][0][:48] if r["samples"] else "")
        print(f"{r['domain']:<24}{icon:<16}{str(r['after'] or '-'):>7}  {s}",flush=True)
    print("SEAM_PHASE_DONE",flush=True)

if __name__=="__main__":
    main()
