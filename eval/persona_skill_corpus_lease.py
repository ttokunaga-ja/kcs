#!/usr/bin/env python3
"""Descriptor-bound leases for the opaque Rust persona workspace."""
from __future__ import annotations
import argparse, contextlib, hashlib, hmac, json, os, re, secrets, stat, sys
from datetime import datetime, timezone
from pathlib import Path
if os.name == "nt": import msvcrt
else: import fcntl

OWNER_FILE="persona-workspace-owner.json"; LEASE_FILE="lease.json"; LOCK_FILE=".lease.lock"; RECOVERY_LOG="lease-recovery.jsonl"
MAX_OWNER_BYTES=16*1024; MAX_SCOPE_CONTROLS=20; MAX_OWNER_LABEL_BYTES=256; MAX_RECOVERY_REASON_BYTES=2048; MAX_RECOVERY_LOG_BYTES=64*1024
_DIGEST=re.compile(r"^sha256:[0-9a-f]{64}$"); _SESSION=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"); _COMPONENT=re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
class LeaseError(RuntimeError): pass
def _platform():
    if not isinstance(getattr(os,"O_DIRECTORY",None),int) or not getattr(os,"O_DIRECTORY") or not isinstance(getattr(os,"O_NOFOLLOW",None),int) or not getattr(os,"O_NOFOLLOW"): raise LeaseError("descriptor-safe lease operations require O_DIRECTORY and O_NOFOLLOW")
def _component(value,label):
    if not isinstance(value,str) or _COMPONENT.fullmatch(value) is None or value in (".",".."): raise LeaseError(f"{label} must be a safe direct component")
    return value
def _digest(value):
    if not isinstance(value,str) or _DIGEST.fullmatch(value) is None: raise LeaseError("expected owner digest must be sha256:<lowercase hex>")
    return value
def _session(value):
    if not isinstance(value,str) or _SESSION.fullmatch(value) is None: raise LeaseError("session must be 1-128 ASCII letters, digits, dot, underscore, colon, or hyphen")
def _owner_label(value):
    if value is not None and (not isinstance(value,str) or len(value.encode("utf-8"))>MAX_OWNER_LABEL_BYTES): raise LeaseError("owner label must be null or at most 256 UTF-8 bytes")
def _reason(value):
    if not isinstance(value,str) or not value.strip() or len(value.strip().encode("utf-8"))>MAX_RECOVERY_REASON_BYTES: raise LeaseError("recovery reason must be non-empty and at most 2048 UTF-8 bytes")
    return value.strip()
def _regular(meta,label):
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1: raise LeaseError(f"{label} must be a single-link regular file")
def _same(a,b): return (a.st_dev,a.st_ino,a.st_size,a.st_nlink)==(b.st_dev,b.st_ino,b.st_size,b.st_nlink)
def _directory(meta,label):
    static=label in ("_control","_control/personas","_control/scopes") or label.startswith("_control/scopes/") and label.count("/")==2
    mode=0o500 if static else 0o700
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=os.geteuid() or stat.S_IMODE(meta.st_mode)!=mode: raise LeaseError(f"{label} must be euid-owned mode {mode:04o} directory")
def _root(root):
    _platform(); raw=os.fspath(root)
    if not isinstance(raw,str) or not raw.startswith("/") or raw.startswith("//") or "/./" in raw or raw.endswith("/.") or "/../" in raw or raw.endswith("/..") or raw.endswith("/"): raise LeaseError("workspace root must be absolute and normalized")
    if sys.platform=="darwin" and (raw=="/tmp" or raw.startswith("/tmp/") or raw=="/var" or raw.startswith("/var/")): raw="/private"+raw
    supplied=Path(raw)
    path=supplied; descriptor=None
    try:
        descriptor=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        for part in path.parts[1:]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor); os.close(descriptor); descriptor=nxt
        return descriptor
    except OSError as e:
        if descriptor is not None: os.close(descriptor)
        raise LeaseError(f"cannot bind workspace root: {e}") from e
    except BaseException:
        if descriptor is not None: os.close(descriptor)
        raise
def _dir(parent,name,label):
    _component(name,label)
    try: fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    except OSError as e: raise LeaseError(f"cannot open {label}: {e}") from e
    try:
        _directory(os.fstat(fd),label)
        return fd
    except BaseException: os.close(fd); raise
def _bytes(directory,name,label,maximum):
    try:
        before=os.stat(name,dir_fd=directory,follow_symlinks=False); _regular(before,label)
        if before.st_size>maximum: raise LeaseError(f"{label} exceeds {maximum} bytes")
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    except OSError as e: raise LeaseError(f"cannot read {label}: {e}") from e
    try:
        opened=os.fstat(fd); _regular(opened,label)
        if not _same(before,opened): raise LeaseError(f"{label} changed while opening")
        chunks=[]
        while sum(map(len,chunks))<=maximum:
            part=os.read(fd,min(8192,maximum+1-sum(map(len,chunks))))
            if not part: break
            chunks.append(part)
        data=b"".join(chunks)
        if len(data)>maximum: raise LeaseError(f"{label} exceeds {maximum} bytes")
        after=os.stat(name,dir_fd=directory,follow_symlinks=False); _regular(after,label)
        if not _same(opened,after): raise LeaseError(f"{label} changed while reading")
        return data
    finally: os.close(fd)
def _bind_owner(root,expected):
    expected=_digest(expected)
    try:
        named=os.stat(OWNER_FILE,dir_fd=root,follow_symlinks=False); _regular(named,OWNER_FILE)
        if named.st_size>MAX_OWNER_BYTES: raise LeaseError(f"{OWNER_FILE} exceeds {MAX_OWNER_BYTES} bytes")
        fd=os.open(OWNER_FILE,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=root)
    except OSError as e: raise LeaseError(f"cannot read {OWNER_FILE}: {e}") from e
    try:
        opened=os.fstat(fd); _regular(opened,OWNER_FILE)
        if not _same(named,opened): raise LeaseError(f"{OWNER_FILE} changed while opening")
        data=_owner_bytes(fd)
        if not hmac.compare_digest("sha256:"+hashlib.sha256(data).hexdigest(),expected): raise LeaseError("workspace owner digest mismatch")
        return fd,opened,expected
    except BaseException:
        os.close(fd); raise
def _owner_bytes(fd):
    os.lseek(fd,0,os.SEEK_SET); data=b""
    while len(data)<=MAX_OWNER_BYTES:
        part=os.read(fd,min(8192,MAX_OWNER_BYTES+1-len(data)))
        if not part: break
        data+=part
    if len(data)>MAX_OWNER_BYTES: raise LeaseError(f"{OWNER_FILE} exceeds {MAX_OWNER_BYTES} bytes")
    return data
def _recheck_owner(root,fd,bound,expected):
    now=os.fstat(fd); _regular(now,OWNER_FILE)
    named=os.stat(OWNER_FILE,dir_fd=root,follow_symlinks=False); _regular(named,OWNER_FILE)
    if not _same(bound,now) or not _same(now,named): raise LeaseError(f"{OWNER_FILE} changed during lease operation")
    if not hmac.compare_digest("sha256:"+hashlib.sha256(_owner_bytes(fd)).hexdigest(),expected): raise LeaseError("workspace owner digest changed during lease operation")
    after=os.fstat(fd); named_after=os.stat(OWNER_FILE,dir_fd=root,follow_symlinks=False); _regular(after,OWNER_FILE); _regular(named_after,OWNER_FILE)
    if not _same(bound,after) or not _same(after,named_after): raise LeaseError(f"{OWNER_FILE} changed during lease operation")
def _recheck_static(bound):
    for fd,metadata,label in bound:
        now=os.fstat(fd); _directory(now,label)
        if not _same(metadata,now): raise LeaseError(f"{label} changed during lease operation")
def _recheck_binding(rootfd,ownerfd,bound,digest,static):
    _recheck_static(static); _recheck_owner(rootfd,ownerfd,bound,digest); _recheck_static(static)
def _close_bound(rootfd,parent,ownerfd,bound,digest,static,scope=None):
    try: _recheck_binding(rootfd,ownerfd,bound,digest,static)
    finally:
        try: os.close(ownerfd)
        finally:
            try:
                if scope is not None: os.close(scope)
            finally:
                try: os.close(parent)
                finally:
                    try:
                        for fd,_,_ in reversed(static): os.close(fd)
                    finally: os.close(rootfd)
def _parent(root_path,expected,persona):
    persona=_component(persona,"persona id"); root=_root(root_path)
    try:
        ownerfd,bound,expected=_bind_owner(root,expected); control=_dir(root,"_control","_control"); people=_dir(control,"personas","_control/personas"); parent=_dir(people,persona,f"_control/personas/{persona}")
        return root,parent,ownerfd,bound,persona,[(control,os.fstat(control),"_control"),(people,os.fstat(people),"_control/personas")]
    except BaseException:
        try: os.close(ownerfd)
        except UnboundLocalError: pass
        for fd in (locals().get("people"),locals().get("control")):
            if fd is not None: os.close(fd)
        os.close(root); raise
def _scope(root_path,expected,persona,scope):
    scope=_component(scope,"scope id"); root,parent,ownerfd,bound,persona,static=_parent(root_path,expected,persona)
    try:
        control=static[0][0]
        try:
            scopes=_dir(control,"scopes","_control/scopes")
            pscopes=_dir(scopes,persona,f"_control/scopes/{persona}"); child=_dir(pscopes,scope,f"_control/scopes/{persona}/{scope}")
        except BaseException:
            try: os.close(pscopes)
            except UnboundLocalError: pass
            try: os.close(scopes)
            except UnboundLocalError: pass
            raise
        static.extend([(scopes,os.fstat(scopes),"_control/scopes"),(pscopes,os.fstat(pscopes),f"_control/scopes/{persona}")])
        return root,parent,child,ownerfd,bound,persona,scope,static
    except BaseException:
        os.close(ownerfd); os.close(parent)
        for fd,_,_ in reversed(static): os.close(fd)
        os.close(root); raise
def _existing(directory,name,label):
    try: fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    except FileExistsError:
        try: fd=os.open(name,os.O_RDWR|os.O_NOFOLLOW,dir_fd=directory)
        except OSError as e: raise LeaseError(f"cannot open {label}: {e}") from e
    except OSError as e: raise LeaseError(f"cannot create {label}: {e}") from e
    try: _regular(os.fstat(fd),label); return fd
    except BaseException: os.close(fd); raise
@contextlib.contextmanager
def _guard(directory,label):
    fd=_existing(directory,LOCK_FILE,f"{label}/{LOCK_FILE}")
    try:
        if os.name=="nt": msvcrt.locking(fd,msvcrt.LK_LOCK,1)
        else: fcntl.flock(fd,fcntl.LOCK_EX)
        try: yield
        finally:
            if os.name=="nt": msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
            else: fcntl.flock(fd,fcntl.LOCK_UN)
    finally: os.close(fd)
def _read(directory,label):
    try: value=json.loads(_bytes(directory,LEASE_FILE,label,MAX_OWNER_BYTES))
    except (ValueError,UnicodeDecodeError) as e: raise LeaseError(f"invalid {label}") from e
    if not isinstance(value,dict): raise LeaseError(f"invalid {label}")
    return value
def _write_all(fd,data):
    offset=0
    while offset<len(data):
        written=os.write(fd,data[offset:])
        if written<=0: raise LeaseError("short lease file write")
        offset+=written
def _new(directory,payload,label):
    data=(json.dumps(payload,ensure_ascii=False,sort_keys=True)+"\n").encode()
    try: fd=os.open(LEASE_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    except OSError as e: raise LeaseError(f"cannot create {label}: {e}") from e
    try:
        _write_all(fd,data); os.fsync(fd); _regular(os.fstat(fd),label)
    finally: os.close(fd)
    os.fsync(directory)
def _append(directory,label,payload):
    fd=_existing(directory,RECOVERY_LOG,f"{label}/{RECOVERY_LOG}")
    try:
        data=(json.dumps(payload,ensure_ascii=False,sort_keys=True)+"\n").encode()
        if os.fstat(fd).st_size+len(data)>MAX_RECOVERY_LOG_BYTES: raise LeaseError(f"{label}/{RECOVERY_LOG} exceeds {MAX_RECOVERY_LOG_BYTES} bytes")
        os.lseek(fd,0,os.SEEK_END); _write_all(fd,data); os.fsync(fd)
    finally: os.close(fd)
    os.fsync(directory)
def _public(payload): return {k:v for k,v in payload.items() if k!="release_token_sha256"}
def _token(token): return hashlib.sha256(token.encode()).hexdigest()
def _parent_payload(directory,persona,digest):
    value=_read(directory,f"_control/personas/{persona}/{LEASE_FILE}")
    if set(value)!={"schema_version","persona_id","owner_digest","session","owner_label","claimed_at","release_token_sha256"} or value.get("schema_version")!=1 or value.get("persona_id")!=persona or value.get("owner_digest")!=digest or not isinstance(value.get("session"),str) or not isinstance(value.get("claimed_at"),str) or not isinstance(value.get("release_token_sha256"),str): raise LeaseError(f"invalid persona lease: {persona}")
    _owner_label(value["owner_label"])
    return value
def _scope_payload(directory,persona,scope,digest):
    value=_read(directory,f"_control/scopes/{persona}/{scope}/{LEASE_FILE}")
    if set(value)!={"schema_version","persona_id","scope_id","owner_digest","parent_session","worker_session","owner_label","claimed_at","release_token_sha256"} or value.get("schema_version")!=1 or value.get("persona_id")!=persona or value.get("scope_id")!=scope or value.get("owner_digest")!=digest or not isinstance(value.get("parent_session"),str) or not isinstance(value.get("worker_session"),str) or not isinstance(value.get("claimed_at"),str) or not isinstance(value.get("release_token_sha256"),str): raise LeaseError(f"invalid scope lease: {persona}/{scope}")
    _owner_label(value["owner_label"])
    return value
def _active(root,persona,digest):
    control=_dir(root,"_control","_control")
    try:
        scopes=_dir(control,"scopes","_control/scopes")
        try: directory=_dir(scopes,persona,f"_control/scopes/{persona}")
        finally: os.close(scopes)
    finally: os.close(control)
    try:
        names=os.listdir(directory)
        if len(names)>MAX_SCOPE_CONTROLS: raise LeaseError(f"too many scope controls for {persona}")
        active=[]
        for scope in names:
            _component(scope,"scope control entry"); child=_dir(directory,scope,f"_control/scopes/{persona}/{scope}")
            try:
                try: os.stat(LEASE_FILE,dir_fd=child,follow_symlinks=False)
                except FileNotFoundError: continue
                _scope_payload(child,persona,scope,digest); active.append(scope)
            finally: os.close(child)
        return active
    finally: os.close(directory)
def claim(root:Path,persona_id:str,expected_owner_digest:str,session:str,owner:str|None)->dict[str,object]:
    _session(session); _owner_label(owner); expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,ownerfd,bound,persona,static=_parent(root,expected_owner_digest,persona_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"):
            _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static); token=secrets.token_urlsafe(32); value={"schema_version":1,"persona_id":persona,"owner_digest":expected_owner_digest,"session":session,"owner_label":owner,"claimed_at":datetime.now(timezone.utc).isoformat(),"release_token_sha256":_token(token)}; _new(parent,value,f"_control/personas/{persona}/{LEASE_FILE}"); output=_public(value); output["release_token"]=token; return output
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static)
def read_lease(root:Path,persona_id:str,expected_owner_digest:str)->dict[str,object]:
    expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,ownerfd,bound,persona,static=_parent(root,expected_owner_digest,persona_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"): _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static); return _public(_parent_payload(parent,persona,expected_owner_digest))
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static)
def release(root:Path,persona_id:str,expected_owner_digest:str,token:str)->dict[str,object]:
    if not token: raise LeaseError("release token must not be empty")
    expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,ownerfd,bound,persona,static=_parent(root,expected_owner_digest,persona_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"):
            value=_parent_payload(parent,persona,expected_owner_digest)
            if not hmac.compare_digest(value["release_token_sha256"],_token(token)): raise LeaseError(f"release token mismatch for {persona}")
            active=_active(rootfd,persona,expected_owner_digest)
            if active: raise LeaseError(f"cannot release parent persona lease with active scopes: {active}")
            _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static)
            os.unlink(LEASE_FILE,dir_fd=parent); os.fsync(parent); return _public(value)
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static)
def recover(root:Path,persona_id:str,expected_owner_digest:str,expected_session:str,reason:str)->dict[str,object]:
    _session(expected_session); reason=_reason(reason)
    expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,ownerfd,bound,persona,static=_parent(root,expected_owner_digest,persona_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"):
            value=_parent_payload(parent,persona,expected_owner_digest)
            if value["session"]!=expected_session: raise LeaseError(f"lease session changed for {persona}; recovery refused")
            active=_active(rootfd,persona,expected_owner_digest)
            if active: raise LeaseError(f"cannot recover parent persona lease with active scopes: {active}")
            _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static)
            receipt={"schema_version":1,"action":"forced-recovery","recovered_at":datetime.now(timezone.utc).isoformat(),"reason":reason.strip(),"lease":_public(value)}; _append(parent,f"_control/personas/{persona}",receipt); os.unlink(LEASE_FILE,dir_fd=parent); os.fsync(parent); return receipt
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static)
def scope_claim(root:Path,persona_id:str,scope_id:str,expected_owner_digest:str,parent_session:str,worker_session:str,owner:str|None)->dict[str,object]:
    _session(parent_session); _session(worker_session); _owner_label(owner); expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,scope,ownerfd,bound,persona,scope_id,static=_scope(root,expected_owner_digest,persona_id,scope_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"):
            if _parent_payload(parent,persona,expected_owner_digest)["session"]!=parent_session: raise LeaseError(f"active parent persona lease does not match for {persona}")
            with _guard(scope,f"_control/scopes/{persona}/{scope_id}"):
                _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static); token=secrets.token_urlsafe(32); value={"schema_version":1,"persona_id":persona,"scope_id":scope_id,"owner_digest":expected_owner_digest,"parent_session":parent_session,"worker_session":worker_session,"owner_label":owner,"claimed_at":datetime.now(timezone.utc).isoformat(),"release_token_sha256":_token(token)}; _new(scope,value,f"_control/scopes/{persona}/{scope_id}/{LEASE_FILE}"); output=_public(value); output["release_token"]=token; return output
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static,scope)
def read_scope_lease(root:Path,persona_id:str,scope_id:str,expected_owner_digest:str)->dict[str,object]:
    expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,scope,ownerfd,bound,persona,scope_id,static=_scope(root,expected_owner_digest,persona_id,scope_id)
    try:
        with _guard(scope,f"_control/scopes/{persona}/{scope_id}"): _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static); return _public(_scope_payload(scope,persona,scope_id,expected_owner_digest))
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static,scope)
def scope_release(root:Path,persona_id:str,scope_id:str,expected_owner_digest:str,parent_session:str,token:str)->dict[str,object]:
    if not token: raise LeaseError("release token must not be empty")
    expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,scope,ownerfd,bound,persona,scope_id,static=_scope(root,expected_owner_digest,persona_id,scope_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"):
            if _parent_payload(parent,persona,expected_owner_digest)["session"]!=parent_session: raise LeaseError(f"active parent persona lease does not match for {persona}")
            with _guard(scope,f"_control/scopes/{persona}/{scope_id}"):
                value=_scope_payload(scope,persona,scope_id,expected_owner_digest)
                if value["parent_session"]!=parent_session or not hmac.compare_digest(value["release_token_sha256"],_token(token)): raise LeaseError(f"release token or parent session mismatch for {persona}/{scope_id}")
                _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static)
                os.unlink(LEASE_FILE,dir_fd=scope); os.fsync(scope); return _public(value)
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static,scope)
def scope_recover(root:Path,persona_id:str,scope_id:str,expected_owner_digest:str,parent_session:str,expected_worker_session:str,reason:str)->dict[str,object]:
    _session(expected_worker_session); reason=_reason(reason)
    expected_owner_digest=_digest(expected_owner_digest); rootfd,parent,scope,ownerfd,bound,persona,scope_id,static=_scope(root,expected_owner_digest,persona_id,scope_id)
    try:
        with _guard(parent,f"_control/personas/{persona}"):
            if _parent_payload(parent,persona,expected_owner_digest)["session"]!=parent_session: raise LeaseError(f"active parent persona lease does not match for {persona}")
            with _guard(scope,f"_control/scopes/{persona}/{scope_id}"):
                value=_scope_payload(scope,persona,scope_id,expected_owner_digest)
                if value["parent_session"]!=parent_session or value["worker_session"]!=expected_worker_session: raise LeaseError(f"scope lease changed for {persona}/{scope_id}; recovery refused")
                _recheck_binding(rootfd,ownerfd,bound,expected_owner_digest,static)
                receipt={"schema_version":1,"action":"forced-recovery","recovered_at":datetime.now(timezone.utc).isoformat(),"reason":reason.strip(),"lease":_public(value)}; _append(scope,f"_control/scopes/{persona}/{scope_id}",receipt); os.unlink(LEASE_FILE,dir_fd=scope); os.fsync(scope); return receipt
    finally: _close_bound(rootfd,parent,ownerfd,bound,expected_owner_digest,static,scope)
def _parser():
    parser=argparse.ArgumentParser(description="Manage opaque workspace persona and scope leases.",allow_abbrev=False); subs=parser.add_subparsers(dest="command",required=True)
    for command in ("claim","show","release","recover","scope-claim","scope-show","scope-release","scope-recover"):
        item=subs.add_parser(command,allow_abbrev=False); item.add_argument("--root",type=Path,required=True); item.add_argument("--persona",required=True); item.add_argument("--owner-digest",dest="expected_owner_digest",required=True)
        if command.startswith("scope-"): item.add_argument("--scope-id",required=True)
        if command=="claim": item.add_argument("--session",required=True); item.add_argument("--owner")
        elif command=="release": item.add_argument("--token",required=True)
        elif command=="recover": item.add_argument("--expected-session",required=True); item.add_argument("--reason",required=True)
        elif command=="scope-claim": item.add_argument("--parent-session",required=True); item.add_argument("--worker-session",required=True); item.add_argument("--owner")
        elif command=="scope-release": item.add_argument("--parent-session",required=True); item.add_argument("--token",required=True)
        elif command=="scope-recover": item.add_argument("--parent-session",required=True); item.add_argument("--expected-worker-session",required=True); item.add_argument("--reason",required=True)
    return parser
def main():
    a=_parser().parse_args()
    try:
        if a.command=="claim": out=claim(a.root,a.persona,a.expected_owner_digest,a.session,a.owner)
        elif a.command=="show": out=read_lease(a.root,a.persona,a.expected_owner_digest)
        elif a.command=="release": out=release(a.root,a.persona,a.expected_owner_digest,a.token)
        elif a.command=="recover": out=recover(a.root,a.persona,a.expected_owner_digest,a.expected_session,a.reason)
        elif a.command=="scope-claim": out=scope_claim(a.root,a.persona,a.scope_id,a.expected_owner_digest,a.parent_session,a.worker_session,a.owner)
        elif a.command=="scope-show": out=read_scope_lease(a.root,a.persona,a.scope_id,a.expected_owner_digest)
        elif a.command=="scope-release": out=scope_release(a.root,a.persona,a.scope_id,a.expected_owner_digest,a.parent_session,a.token)
        else: out=scope_recover(a.root,a.persona,a.scope_id,a.expected_owner_digest,a.parent_session,a.expected_worker_session,a.reason)
    except (OSError,LeaseError) as e: print(f"[error] {e}",file=sys.stderr); return 1
    print(json.dumps(out,ensure_ascii=False,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
