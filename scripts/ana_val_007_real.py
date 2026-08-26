#!/usr/bin/env python3
import argparse, copy, hashlib, json, os, sys, threading, time, uuid
from pathlib import Path
from urllib import request, error

ANN = "ana.continuityos/"
NS = "ana-val-007-real"

def jdump(x): return json.dumps(x, sort_keys=True, separators=(",", ":"))
def digest_action(a): return hashlib.sha256(jdump(a).encode()).hexdigest()

class API:
    def __init__(self, base, evidence):
        self.base = base.rstrip("/")
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.seq_lock = threading.Lock()

    def call(self, method, path, body=None, label=None, client_id="main"):
        with self.seq_lock:
            self.seq += 1
            seq = self.seq
        data = None if body is None else json.dumps(body).encode()
        req = request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        ts = time.time()
        try:
            with request.urlopen(req, timeout=30) as r:
                raw = r.read()
                status = r.status
        except error.HTTPError as e:
            raw = e.read()
            status = e.code
        parsed = None
        try: parsed = json.loads(raw.decode()) if raw else None
        except Exception: parsed = raw.decode(errors="replace")
        req_rv = None
        if isinstance(body, dict):
            req_rv = (body.get("metadata") or {}).get("resourceVersion")
        resp_rv = None
        if isinstance(parsed, dict):
            resp_rv = (parsed.get("metadata") or {}).get("resourceVersion")
        rec = {
            "seq": seq, "label": label, "client_id": client_id,
            "utc_epoch": ts, "method": method, "path": path,
            "request": body, "requestResourceVersion": req_rv,
            "status": status, "response": parsed,
            "responseResourceVersion": resp_rv
        }
        (self.evidence / f"http-{seq:04d}-{label or 'call'}.json").write_text(
            json.dumps(rec, indent=2, sort_keys=True)
        )
        return status, parsed

    def create_ns(self):
        st, obj = self.call("POST", "/api/v1/namespaces",
            {"apiVersion":"v1","kind":"Namespace","metadata":{"name":NS}},
            "namespace-create")
        if st not in (201,409): raise RuntimeError((st,obj))

def action(target="dep", recipient="prod", tool="kubernetes", environment="test", op="deploy"):
    return {"target":target,"recipient":recipient,"tool":tool,"environment":environment,"operation":op}

def annotations(authority="CURRENT", av="1", pav="1", action_obj=None, consequence="none", receipt="none"):
    a = action_obj or action()
    return {
        ANN+"authorityState": authority,
        ANN+"authorityVersion": av,
        ANN+"parentAuthorityVersion": pav,
        ANN+"actionDigest": digest_action(a),
        ANN+"recipient": a["recipient"],
        ANN+"tool": a["tool"],
        ANN+"environment": a["environment"],
        ANN+"target": a["target"],
        ANN+"consequence": consequence,
        ANN+"commitId": receipt,
    }

def dep(name, anns=None):
    return {
      "apiVersion":"apps/v1","kind":"Deployment",
      "metadata":{"name":name,"namespace":NS,"annotations":anns or annotations()},
      "spec":{"replicas":0,"selector":{"matchLabels":{"app":name}},
              "template":{"metadata":{"labels":{"app":name}},
                          "spec":{"containers":[{"name":"pause","image":"registry.k8s.io/pause:3.10"}]}}}
    }

def cm(name, state="CURRENT", version="1"):
    return {"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":name,"namespace":NS},
            "data":{"authorityState":state,"authorityVersion":version}}

def path_dep(name): return f"/apis/apps/v1/namespaces/{NS}/deployments/{name}"
def path_deps(): return f"/apis/apps/v1/namespaces/{NS}/deployments"
def path_cm(name): return f"/api/v1/namespaces/{NS}/configmaps/{name}"
def path_cms(): return f"/api/v1/namespaces/{NS}/configmaps"

def create_dep(api, name, anns=None):
    st,o=api.call("POST",path_deps(),dep(name,anns),"create-"+name)
    assert st==201,(st,o); return o
def create_cm(api,name,state="CURRENT",version="1"):
    st,o=api.call("POST",path_cms(),cm(name,state,version),"create-"+name)
    assert st==201,(st,o); return o
def get_dep(api,name,label=None,client_id="main"):
    st,o=api.call("GET",path_dep(name),None,label or "get-"+name,client_id=client_id); assert st==200; return o
def get_cm(api,name,label=None,client_id="main"):
    st,o=api.call("GET",path_cm(name),None,label or "get-"+name,client_id=client_id); assert st==200; return o
def put_dep(api,obj,label,client_id="main"):
    return api.call("PUT",path_dep(obj["metadata"]["name"]),obj,label,client_id=client_id)
def put_cm(api,obj,label,client_id="main"):
    return api.call("PUT",path_cm(obj["metadata"]["name"]),obj,label,client_id=client_id)

def block_reason(obj, intended):
    anns=obj["metadata"]["annotations"]
    if anns.get(ANN+"authorityState")!="CURRENT": return "AUTHORITY_NOT_CURRENT"
    actual={k:anns.get(ANN+k) for k in ("target","recipient","tool","environment")}
    d=digest_action({**intended})
    if d != anns.get(ANN+"actionDigest"): return "ACTION_DIGEST_MISMATCH"
    if actual != {k:intended[k] for k in actual}: return "ACTION_MATERIAL_MISMATCH"
    return None

RESULTS=[]
def record(case, expected, observed, passed, details=None):
    RESULTS.append({"case":case,"expected":expected,"observed":observed,
                    "pass":bool(passed),"details":details or {}})
    print(f"{'PASS' if passed else 'FAIL'} {case}: {observed}")

def commit_obj(o, consequence):
    x=copy.deepcopy(o)
    x["metadata"]["annotations"][ANN+"consequence"]=consequence
    x["metadata"]["annotations"][ANN+"commitId"]=str(uuid.uuid4())
    return x

def run_q(api):
    # Q01
    c=create_cm(api,"q01-auth"); d=create_dep(api,"q01")
    cur=get_cm(api,"q01-auth"); obj=get_dep(api,"q01")
    ok=(cur["data"]["authorityState"]=="CURRENT" and block_reason(obj,action()) is None)
    st,_=put_dep(api,commit_obj(obj,"q01"),"q01-update") if ok else (0,None)
    record("Q01","ALLOW/UPDATE",st,st==200)

    # Q02
    d=create_dep(api,"q02"); old=get_dep(api,"q02")
    now=copy.deepcopy(old); now["metadata"]["annotations"][ANN+"consequence"]="intervening"
    st1,_=put_dep(api,now,"q02-intervening")
    st2,_=put_dep(api,commit_obj(old,"stale"),"q02-stale")
    record("Q02","409 / no update",st2,st1==200 and st2==409)

    # Q03
    create_cm(api,"q03-auth","REVOKED","2"); d=create_dep(api,"q03")
    auth=get_cm(api,"q03-auth"); obj=get_dep(api,"q03")
    blocked=auth["data"]["authorityState"]!="CURRENT"
    record("Q03","BLOCK","client-block" if blocked else "not-blocked",blocked)

    # Q04
    create_cm(api,"q04-auth"); create_dep(api,"q04")
    auth=get_cm(api,"q04-auth"); obj=get_dep(api,"q04")
    pre=(auth["data"]["authorityState"]=="CURRENT")
    rev=copy.deepcopy(auth); rev["data"]["authorityState"]="REVOKED"; rev["data"]["authorityVersion"]="2"
    sr,_=put_cm(api,rev,"q04-revoke")
    st,_=put_dep(api,commit_obj(obj,"q04-after-revoke"),"q04-consequence")
    record("Q04","EXPECT VULNERABILITY: update succeeds",st,pre and sr==200 and st==200)

    # Q05
    create_cm(api,"q05-auth"); obj=create_dep(api,"q05")
    prepared=get_dep(api,"q05")
    mutated=action(recipient="other")
    blocked=block_reason(prepared,mutated) is not None
    record("Q05","BLOCK by action digest","client-block" if blocked else "not-blocked",blocked)

    # Q06
    create_cm(api,"q06-auth"); obj=create_dep(api,"q06",annotations(action_obj=action(target="q06")))
    prepared=get_dep(api,"q06")
    substituted=action(target="different-deployment")
    blocked=block_reason(prepared,substituted) is not None
    record("Q06","BLOCK by CAI/target binding","client-block" if blocked else "not-blocked",blocked)

    # Q07
    create_cm(api,"q07-auth"); create_dep(api,"q07"); base=get_dep(api,"q07")
    a=commit_obj(base,"A"); b=commit_obj(base,"B")
    out=[]
    def f(x,label): out.append(api.call("PUT",path_dep("q07"),x,label,client_id=label)[0])
    t1=threading.Thread(target=f,args=(a,"q07-A")); t2=threading.Thread(target=f,args=(b,"q07-B"))
    t1.start(); t2.start(); t1.join(); t2.join()
    record("Q07","at most one succeeds",sorted(out),out.count(200)==1 and out.count(409)==1)

    # Q08
    create_dep(api,"q08"); obj=get_dep(api,"q08")
    st,_=put_dep(api,commit_obj(obj,"q08"),"q08-update")
    record("Q08","UPDATE",st,st==200)

    # Q09
    create_dep(api,"q09"); old=get_dep(api,"q09")
    rev=copy.deepcopy(old); rev["metadata"]["annotations"][ANN+"authorityState"]="REVOKED"; rev["metadata"]["annotations"][ANN+"authorityVersion"]="2"
    sr,_=put_dep(api,rev,"q09-revoke")
    sc,_=put_dep(api,commit_obj(old,"q09-consequence"),"q09-stale-consequence")
    record("Q09","409/no consequence",sc,sr==200 and sc==409)

    # Q10
    create_dep(api,"q10"); old=get_dep(api,"q10")
    sc,_=put_dep(api,commit_obj(old,"q10-consequence"),"q10-consequence")
    latest=get_dep(api,"q10","q10-get-after")
    rev=copy.deepcopy(latest); rev["metadata"]["annotations"][ANN+"authorityState"]="REVOKED"; rev["metadata"]["annotations"][ANN+"authorityVersion"]="2"
    sr,_=put_dep(api,rev,"q10-revoke-after")
    record("Q10","consequence UPDATE then revocation",{"consequence":sc,"revoke":sr},sc==200 and sr==200)

    # Q11
    create_dep(api,"q11"); old=get_dep(api,"q11")
    change=copy.deepcopy(old); change["metadata"]["annotations"][ANN+"authorityVersion"]="2"
    s1,_=put_dep(api,change,"q11-authority-version-change")
    s2,_=put_dep(api,commit_obj(old,"q11-stale"),"q11-stale-consequence")
    record("Q11","409",s2,s1==200 and s2==409)

    # Q12
    create_dep(api,"q12"); old=get_dep(api,"q12")
    change=copy.deepcopy(old); change["metadata"]["annotations"][ANN+"parentAuthorityVersion"]="2"
    s1,_=put_dep(api,change,"q12-parent-version-change")
    s2,_=put_dep(api,commit_obj(old,"q12-stale"),"q12-stale-consequence")
    record("Q12","409",s2,s1==200 and s2==409)

    # Q13
    create_dep(api,"q13"); obj=get_dep(api,"q13")
    obj["metadata"]["annotations"][ANN+"actionDigest"]="bad-digest"
    blocked=block_reason(obj,action()) is not None
    record("Q13","BLOCK","client-block" if blocked else "not-blocked",blocked)

    # Q14 all four material dimensions
    sub={}
    for field in ("recipient","target","tool","environment"):
        name="q14-"+field
        base_action=action(target=name)
        create_dep(api,name,annotations(action_obj=base_action))
        obj=get_dep(api,name)
        m=dict(base_action); m[field]="mutated-"+field
        sub[field]=block_reason(obj,m) is not None
    record("Q14","BLOCK material mutation",sub,all(sub.values()))

    # Q15
    create_dep(api,"q15"); old=get_dep(api,"q15")
    s1,_=put_dep(api,commit_obj(old,"first"),"q15-first")
    s2,_=put_dep(api,commit_obj(old,"replay"),"q15-replay")
    record("Q15","409/no second transition",s2,s1==200 and s2==409)

    # Q16
    create_dep(api,"q16"); old=get_dep(api,"q16"); x=commit_obj(old,"duplicate")
    out=[]
    def f16(label): out.append(api.call("PUT",path_dep("q16"),copy.deepcopy(x),label,client_id=label)[0])
    t1=threading.Thread(target=f16,args=("q16-A",)); t2=threading.Thread(target=f16,args=("q16-B",))
    t1.start(); t2.start(); t1.join(); t2.join()
    record("Q16","one update maximum",sorted(out),out.count(200)==1 and out.count(409)==1)

    # Q17
    create_dep(api,"q17"); old=get_dep(api,"q17")
    out=[]
    def f17(c,label): out.append(api.call("PUT",path_dep("q17"),commit_obj(old,c),label,client_id=label)[0])
    t1=threading.Thread(target=f17,args=("A","q17-A")); t2=threading.Thread(target=f17,args=("B","q17-B"))
    t1.start(); t2.start(); t1.join(); t2.join()
    record("Q17","one maximum",sorted(out),out.count(200)==1 and out.count(409)==1)

    # Q18
    create_dep(api,"q18-a"); create_dep(api,"q18-b")
    a=get_dep(api,"q18-a"); b=get_dep(api,"q18-b")
    sa,_=put_dep(api,commit_obj(a,"A"),"q18-A")
    sb,_=put_dep(api,commit_obj(b,"B"),"q18-B")
    record("Q18","both may succeed",{"A":sa,"B":sb},sa==200 and sb==200)

    # Q19
    create_dep(api,"q19",annotations(authority="EXPIRED"))
    obj=get_dep(api,"q19")
    blocked=block_reason(obj,action()) is not None
    record("Q19","BLOCK","client-block" if blocked else "not-blocked",blocked)

    # Q20
    create_dep(api,"q20"); old=get_dep(api,"q20")
    commit_id=str(uuid.uuid4()); x=copy.deepcopy(old)
    x["metadata"]["annotations"][ANN+"consequence"]="q20"
    x["metadata"]["annotations"][ANN+"commitId"]=commit_id
    st,new=put_dep(api,x,"q20-consequence")
    receipt={
        "ActionDigest": new["metadata"]["annotations"].get(ANN+"actionDigest") if st==200 else None,
        "authorityVersion": new["metadata"]["annotations"].get(ANN+"authorityVersion") if st==200 else None,
        "resultingResourceVersion": new["metadata"].get("resourceVersion") if st==200 else None,
        "commitId": new["metadata"]["annotations"].get(ANN+"commitId") if st==200 else None,
    }
    ok=st==200 and all(receipt.values()) and receipt["commitId"]==commit_id
    record("Q20","receipt binding PASS",receipt,ok)

    # Q21
    auth=create_cm(api,"q21-auth"); create_dep(api,"q21")
    ar=get_cm(api,"q21-auth"); d=get_dep(api,"q21")
    rev=copy.deepcopy(ar); rev["data"]["authorityState"]="REVOKED"; rev["data"]["authorityVersion"]="2"
    sr,_=put_cm(api,rev,"q21-revoke")
    sd,_=put_dep(api,commit_obj(d,"q21-after-revoke"),"q21-consequence")
    record("Q21","EXPECT VULNERABILITY: update can succeed",sd,sr==200 and sd==200)

    # Q22
    auth=create_cm(api,"q22-auth"); create_dep(api,"q22")
    d_old=get_dep(api,"q22")
    d_now=copy.deepcopy(d_old); d_now["metadata"]["annotations"][ANN+"consequence"]="intervening"
    si,_=put_dep(api,d_now,"q22-intervening")
    ar=get_cm(api,"q22-auth"); rev=copy.deepcopy(ar); rev["data"]["authorityState"]="REVOKED"
    sr,_=put_cm(api,rev,"q22-revoke")
    sd,_=put_dep(api,commit_obj(d_old,"q22-stale"),"q22-stale")
    record("Q22","Deployment update rejected",sd,si==200 and sr==200 and sd==409)

    # Q23
    auth=create_cm(api,"q23-auth"); create_dep(api,"q23")
    ar=get_cm(api,"q23-auth"); rev=copy.deepcopy(ar); rev["data"]["authorityState"]="REVOKED"; rev["data"]["authorityVersion"]="2"
    sa,_=put_cm(api,rev,"q23-revoke")
    latest=get_dep(api,"q23"); sd,_=put_dep(api,commit_obj(latest,"q23-retried-consequence"),"q23-retry")
    record("Q23","no claim of atomic ANA",{"authority":sa,"deployment_retry":sd},sa==200 and sd==200)

    # Q24
    create_cm(api,"q24-auth"); create_dep(api,"q24")
    ar=get_cm(api,"q24-auth"); d=get_dep(api,"q24")
    sd,_=put_dep(api,commit_obj(d,"q24"),"q24-update") if ar["data"]["authorityState"]=="CURRENT" else (0,None)
    record("Q24","legitimate update succeeds",sd,sd==200)

def run_races(api):
    # Forced-race rule: each R case uses two distinct request clients plus
    # synchronization primitives that make the preregistered serialization
    # order observable. These are controlled interleavings, not a claim that
    # wall-clock simultaneity is itself the security property.

    # R1 — external authority revokes after precheck; Deployment RV unchanged.
    create_cm(api,"r1-auth"); create_dep(api,"r1")
    auth=get_cm(api,"r1-auth","r1-precheck-auth",client_id="R1-precheck")
    d=get_dep(api,"r1","r1-precheck-dep",client_id="R1-precheck")
    pre=(auth["data"]["authorityState"]=="CURRENT")
    barrier=threading.Barrier(3); revoked=threading.Event(); out={}
    def r1_revoke():
        barrier.wait()
        rev=copy.deepcopy(auth); rev["data"]["authorityState"]="REVOKED"; rev["data"]["authorityVersion"]="2"
        out["revoke"]=put_cm(api,rev,"r1-revoke",client_id="R1-revoker")[0]
        revoked.set()
    def r1_consequence():
        barrier.wait(); revoked.wait(30)
        out["consequence"]=put_dep(api,commit_obj(d,"r1-after-revoke"),"r1-consequence",client_id="R1-consequence")[0]
    t1=threading.Thread(target=r1_revoke); t2=threading.Thread(target=r1_consequence)
    t1.start(); t2.start(); barrier.wait(); t1.join(); t2.join()
    record("R1","reproduce K1 vulnerability",out,pre and out.get("revoke")==200 and out.get("consequence")==200)

    # R2 — same-object revocation CAS serializes first, stale consequence rejected.
    create_dep(api,"r2"); old=get_dep(api,"r2","r2-pre-read",client_id="R2-precheck")
    barrier=threading.Barrier(3); revoked=threading.Event(); out={}
    def r2_revoke():
        barrier.wait()
        rev=copy.deepcopy(old); rev["metadata"]["annotations"][ANN+"authorityState"]="REVOKED"; rev["metadata"]["annotations"][ANN+"authorityVersion"]="2"
        out["revoke"]=put_dep(api,rev,"r2-revoke",client_id="R2-revoker")[0]
        revoked.set()
    def r2_consequence():
        barrier.wait(); revoked.wait(30)
        out["consequence"]=put_dep(api,commit_obj(old,"r2-consequence"),"r2-stale-consequence",client_id="R2-consequence")[0]
    t1=threading.Thread(target=r2_revoke); t2=threading.Thread(target=r2_consequence)
    t1.start(); t2.start(); barrier.wait(); t1.join(); t2.join()
    record("R2","stale consequence rejected",out,out.get("revoke")==200 and out.get("consequence")==409)

    # R3 — consequence serializes first. A revoker prepared from the same RV
    # becomes stale, then revocation follows from the new RV.
    create_dep(api,"r3"); old=get_dep(api,"r3","r3-pre-read",client_id="R3-precheck")
    barrier=threading.Barrier(3); consequence_done=threading.Event(); out={}
    def r3_consequence():
        barrier.wait()
        out["consequence"]=put_dep(api,commit_obj(old,"r3-consequence"),"r3-consequence-first",client_id="R3-consequence")[0]
        consequence_done.set()
    def r3_revoke():
        barrier.wait(); consequence_done.wait(30)
        stale=copy.deepcopy(old); stale["metadata"]["annotations"][ANN+"authorityState"]="REVOKED"; stale["metadata"]["annotations"][ANN+"authorityVersion"]="2"
        out["stale_revoke"]=put_dep(api,stale,"r3-stale-revoke",client_id="R3-revoker")[0]
        latest=get_dep(api,"r3","r3-reload-after-conflict",client_id="R3-revoker")
        rev=copy.deepcopy(latest); rev["metadata"]["annotations"][ANN+"authorityState"]="REVOKED"; rev["metadata"]["annotations"][ANN+"authorityVersion"]="2"
        out["revoke_after"]=put_dep(api,rev,"r3-revoke-after",client_id="R3-revoker")[0]
    t1=threading.Thread(target=r3_consequence); t2=threading.Thread(target=r3_revoke)
    t1.start(); t2.start(); barrier.wait(); t1.join(); t2.join()
    record("R3","consequence commits then revocation follows",out,
           out.get("consequence")==200 and out.get("stale_revoke")==409 and out.get("revoke_after")==200)

    # R4 — two consequences submit the same expected RV concurrently.
    create_dep(api,"r4"); old=get_dep(api,"r4","r4-pre-read",client_id="R4-precheck")
    barrier=threading.Barrier(3); out=[]
    def r4_racer(c,label):
        x=commit_obj(old,c); barrier.wait()
        out.append(api.call("PUT",path_dep("r4"),x,label,client_id=label)[0])
    t1=threading.Thread(target=r4_racer,args=("A","R4-A")); t2=threading.Thread(target=r4_racer,args=("B","R4-B"))
    t1.start(); t2.start(); barrier.wait(); t1.join(); t2.join()
    record("R4","exactly one succeeds",sorted(out),out.count(200)==1 and out.count(409)==1)

    # R5 — separate authority object revokes first while Deployment RV is unchanged.
    create_cm(api,"r5-auth"); create_dep(api,"r5")
    ar=get_cm(api,"r5-auth","r5-precheck-auth",client_id="R5-precheck")
    d=get_dep(api,"r5","r5-precheck-dep",client_id="R5-precheck")
    barrier=threading.Barrier(3); revoked=threading.Event(); out={}
    def r5_revoke():
        barrier.wait()
        rev=copy.deepcopy(ar); rev["data"]["authorityState"]="REVOKED"; rev["data"]["authorityVersion"]="2"
        out["revoke"]=put_cm(api,rev,"r5-revoke",client_id="R5-revoker")[0]
        revoked.set()
    def r5_consequence():
        barrier.wait(); revoked.wait(30)
        out["consequence"]=put_dep(api,commit_obj(d,"r5-after-revoke"),"r5-consequence",client_id="R5-consequence")[0]
    t1=threading.Thread(target=r5_revoke); t2=threading.Thread(target=r5_consequence)
    t1.start(); t2.start(); barrier.wait(); t1.join(); t2.join()
    record("R5","separate-object gap reproduced",out,out.get("revoke")==200 and out.get("consequence")==200)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--api",required=True); ap.add_argument("--evidence",required=True)
    a=ap.parse_args()
    api=API(a.api,a.evidence)
    api.create_ns()
    run_q(api); run_races(api)
    out=Path(a.evidence)
    (out/"ANA-VAL-007-REAL-RESULTS.json").write_text(json.dumps(RESULTS,indent=2,sort_keys=True))
    summary={
      "q_pass":sum(r["pass"] for r in RESULTS if r["case"].startswith("Q")),
      "q_total":sum(1 for r in RESULTS if r["case"].startswith("Q")),
      "r_pass":sum(r["pass"] for r in RESULTS if r["case"].startswith("R")),
      "r_total":sum(1 for r in RESULTS if r["case"].startswith("R")),
      "all_pass":all(r["pass"] for r in RESULTS)
    }
    (out/"SUMMARY.json").write_text(json.dumps(summary,indent=2,sort_keys=True))
    print(json.dumps(summary,indent=2))
    sys.exit(0 if summary["all_pass"] else 2)

if __name__=="__main__": main()
