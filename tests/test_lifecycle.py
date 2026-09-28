"""Isolated lifecycle tests: real installer, mocked OS/network; no host changes.
Илья Рублев — https://t.me/Rublev_YouTube
"""
import atexit, base64, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, zipfile, zlib

TEMP = tempfile.TemporaryDirectory(prefix='openflux-lifecycle-')
atexit.register(TEMP.cleanup)
ROOT = pathlib.Path(TEMP.name)
SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'openflux-install.sh'
MOCK_BINARY = b'#!/bin/sh\n# isolated test binary; never an OpenFlux executable\nexit 0\n'
DIGEST = hashlib.sha256(MOCK_BINARY).hexdigest()

STUB = r'''#!/usr/bin/env python3
import base64, json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ['FIXTURE'])
cmd = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root/'calls.log').open('a') as f: f.write(cmd+' '+repr(args)+'\n')
statefile = root/'mock-state.json'
s = json.loads(statefile.read_text()) if statefile.exists() else {}
rc = 0
if cmd == 'uname':
    print('Linux' if args == ['-s'] else os.environ.get('MOCK_ARCH', 'x86_64'))
elif cmd == 'dpkg-query':
    print('install ok installed', end='')
elif cmd == 'apt-get':
    raise SystemExit('unexpected apt-get call in dependency-present fixture')
elif cmd == 'systemctl':
    op = args[0]
    if op == 'show':
        if '--property=DropInPaths' in args: print(os.environ.get('DROP_INS', ''))
        elif 'LoadState' in args: print('loaded' if (root/'etc/systemd/system/openflux.service').exists() else 'not-found')
        else:
            s['shows'] = s.get('shows', 0) + 1
            mode = s.get('health', '')
            if mode == 'restart' and s['shows'] == 3:
                s['pid'] += 1; s['restarts'] += 1
                (root/'var/lib/openflux/cookies.json').write_text('{}')
            print('ActiveState=' + ('active' if s.get('active') else 'inactive'))
            print('SubState=' + ('running' if s.get('active') else 'dead'))
            print('MainPID=' + str(s.get('pid', 0) if s.get('active') else 0))
            print('NRestarts=' + str(s.get('restarts', 0)))
    elif op == 'is-active': rc = 0 if s.get('active') else 3
    elif op == 'is-enabled': rc = 0 if s.get('enabled') else 1
    elif op == 'start':
        if os.environ.get('FAIL_START') and not (root/'failed-once').exists():
            (root/'failed-once').touch(); rc = 1
        else:
            s['active'] = True
            s['pid'] = s.get('pid', 300) + 1
            s['restarts'] = s.get('restarts', 0)
            s['shows'] = 0
            s['health'] = ''
            if os.environ.get('FAIL_RUNTIME') and not (root/'runtime-failed-once').exists():
                (root/'runtime-failed-once').touch()
                s['health'] = os.environ['FAIL_RUNTIME']
                if s['health'] == 'captcha':
                    s['active'] = False
                    with (root/'var/log/openflux/openflux.log').open('a') as f:
                        f.write('Failed to start transport: auth: yandex docs: captcha required\n')
    elif op == 'stop': s['active'] = False
    elif op == 'enable': s['enabled'] = True
    elif op == 'disable': s['enabled'] = False
    elif op in ('daemon-reload', 'reset-failed'): pass
    elif 'status' in args: print('mock status')
    else: raise SystemExit('unexpected systemctl operation '+repr(args))
elif cmd == 'getent':
    if args[0] == 'passwd' and s.get('user'):
        print('openflux-rublev:x:999:999::'+str(root/'var/lib/openflux')+':/usr/sbin/nologin')
    elif args[0] == 'group' and s.get('group'): print('openflux-rublev:x:999:')
    else: rc = 2
elif cmd == 'useradd': s.update(user=True, group=True)
elif cmd == 'userdel': s['user'] = False
elif cmd == 'groupdel': s['group'] = False
elif cmd == 'curl':
    dest = pathlib.Path(args[args.index('-o')+1])
    if any('/releases/download/' in a for a in args):
        data = b'#!/bin/sh\n# isolated test binary; never an OpenFlux executable\nexit 0\n'
        if os.environ.get('BAD_HASH'): data += b'corrupted'
        dest.write_bytes(data)
    else:
        editor = os.environ.get('EDITOR_KIND', 'yandex')
        if editor == 'vyandex':
            config = {'officeActionData':{'action_url':'https://volga.yandex.ru/auth','access_token':'test'},'editorParams':{'idDoc':'test'}}
        elif editor == 'unknown': config = {}
        else:
            config = {'officeActionData':{'editor_config':{'document':{'key':'test','permissions':{'edit': editor != 'readonly'}},'token':'test'},'balancer_url':'https://example.test'}}
        dest.write_text('<html><script id="client-config">'+json.dumps(config)+'</script></html>')
elif cmd == 'install':
    filtered = []
    i = 0
    while i < len(args):
        if args[i] in ('-o','-g'): i += 2
        else: filtered.append(args[i]); i += 1
    rc = subprocess.run(['/usr/bin/install',*filtered]).returncode
elif cmd == 'qrencode':
    link = sys.stdin.read().strip()
    assert link.startswith('openflux://v1/')
    assert args[args.index('-t')+1] in ('PNG','ANSIUTF8')
    dest = args[args.index('-o')+1]
    if dest == '-': print('[mock QR display; payload validated separately]')
    else: pathlib.Path(dest).write_bytes(b'\x89PNG\r\n\x1a\nMOCK')
else: raise SystemExit('unhandled mock '+cmd)
statefile.write_text(json.dumps(s))
sys.exit(rc)
'''

class Fixture:
    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix='case-', dir=ROOT))
        for p in ['etc/systemd/system','etc/logrotate.d','usr/local/bin','usr/local/sbin','var/tmp','var/lib','var/log','var/backups','run/lock','run/systemd/system','mock-bin']:
            (self.root/p).mkdir(parents=True, exist_ok=True)
        (self.root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID=24.04\n')
        text = SOURCE.read_text()
        for prefix in ['/usr/local','/etc','/var','/run']:
            text = text.replace(prefix, str(self.root)+prefix)
        text = re.sub(r"(readonly LINUX_(?:AMD64|ARM64)_SHA=')[0-9a-f]+(')", r'\g<1>' + DIGEST + r'\2', text)
        (self.root/'installer.sh').write_text(text)
        stub = self.root/'mock-bin/stub'
        stub.write_text(STUB); stub.chmod(0o755)
        for cmd in ['uname','dpkg-query','apt-get','systemctl','getent','useradd','userdel','groupdel','curl','install','qrencode']:
            (self.root/'mock-bin'/cmd).symlink_to('stub')
        (self.root/'runner.sh').write_text('source "$FIXTURE/installer.sh"\nneed_root() { :; }\nneed_tty() { TTY_FD=0; }\nsleep() { :; }\nmain "$@"\n')
        self.env = dict(os.environ, FIXTURE=str(self.root), PATH=str(self.root/'mock-bin')+':'+os.environ['PATH'])
    def run(self, arg, answers='', expected=0, **extra):
        if arg == '--install':
            import re
            mode = extra.pop('CLIENT_MODE', '')
            lines = answers.splitlines(keepends=True)
            for i, line in enumerate(lines):
                if re.fullmatch(r'https://disk\.yandex\.ru/i/[A-Za-z0-9_-]+/?\n', line):
                    lines.insert(i + 1, mode + '\n'); break
            answers = ''.join(lines)
        p = subprocess.run(['bash',str(self.root/'runner.sh'),arg],input=answers,text=True,capture_output=True,env=dict(self.env,**extra),timeout=45)
        (self.root/'last.stdout').write_text(p.stdout)
        (self.root/'last.stderr').write_text(p.stderr)
        assert p.returncode == expected, (self.root,arg,p.returncode,p.stdout[-3000:],p.stderr)
        assert not list((self.root/'var/tmp').iterdir()), 'temporary secret/staging data not removed'
        return p
    def exists(self,p): return (self.root/p).exists()
    def read(self,p): return (self.root/p).read_bytes()
    def state(self): return json.loads((self.root/'mock-state.json').read_text())
    def verify_profile(self,transport,url,mode='session'):
        cfg = (self.root/'etc/openflux')
        link = (cfg/'connection.txt').read_text().strip()
        encoded = link.split('openflux://v1/',1)[1]
        raw = zlib.decompress(base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)), -15)
        c = json.loads(raw)
        assert c['secret'] == (cfg/'secret.txt').read_text().strip()
        assert c['context'] == url and c['negotiate'] is (mode == 'session')
        assert c['transports'] == [{'type':transport,'url':url,'priority':100}]
        assert len(c['secret']) == 64
        assert (cfg/'secret.txt').stat().st_mode & 0o777 == 0o640
        assert (cfg/'client.zip').stat().st_mode & 0o777 == 0o600
        assert (cfg/'connection.txt').stat().st_mode & 0o777 == 0o600
        unit = (self.root/'etc/systemd/system/openflux.service').read_text()
        flags = f'--transports={transport}:100 --{transport}-url={url}'
        assert '--encryption-key-file=' in unit
        assert ('Codec = legacy' if mode == 'ios' else 'Codec = batched') in (cfg/'server.conf').read_text()
        assert (cfg/'.profile-mode').read_text().strip() == mode
        if mode == 'ios':
            assert '--negotiate' not in unit and '--transports' not in unit
        else:
            assert '--negotiate '+flags in unit
        with zipfile.ZipFile(cfg/'client.zip') as z:
            assert z.read('secret.txt') == (cfg/'secret.txt').read_bytes()
            assert z.read('connection.txt').decode().strip() == link
            assert ('--negotiate' not in z.read('start-openflux.cmd').decode()) if mode == 'ios' else (flags in z.read('start-openflux.cmd').decode())
            assert b'\r\n' in z.read('start-openflux.cmd')
            assert ('--negotiate' not in z.read('start-openflux.sh').decode()) if mode == 'ios' else (flags in z.read('start-openflux.sh').decode())
            sh = self.root/'client-start.sh'; sh.write_bytes(z.read('start-openflux.sh'))
            subprocess.run(['bash','-n',str(sh)], check=True)
        assert self.state()['active'] and self.state()['enabled']
        assert (self.root/'usr/local/bin/openflux').read_bytes() == MOCK_BINARY

passed=[]
def done(name): passed.append(name); print('PASS',name)
url='https://disk.yandex.ru/i/Testing_123'
f=Fixture(); f.run('--install',url+'\n'); f.verify_profile('yandex',url); done('install: yandex, service, profile and native link')
old_key=f.read('etc/openflux/secret.txt')
url2='https://disk.yandex.ru/i/NewEditor'
f.run('--install',url2+'\n',EDITOR_KIND='vyandex'); f.verify_profile('vyandex',url2)
assert f.read('etc/openflux/secret.txt') == old_key; done('reconfigure: vyandex, same key and matching client flags')
f.run('--uninstall','нет\n'); assert f.exists('etc/openflux/secret.txt'); done('cancel deletion preserves files')
f.run('--qr'); done('QR can be displayed again')
old_conf=f.read('etc/openflux/server.conf'); old_unit=f.read('etc/systemd/system/openflux.service')
f.run('--install',url+'\n',expected=1,BAD_HASH='1')
assert f.read('etc/openflux/server.conf')==old_conf and f.state()['active']; done('bad SHA-256 cannot replace existing install')
f.run('--install',url+'\n',expected=1,FAIL_START='1')
assert f.read('etc/openflux/server.conf')==old_conf
assert f.read('etc/systemd/system/openflux.service')==old_unit
assert f.read('usr/local/bin/openflux')==MOCK_BINARY
assert f.read('etc/openflux/secret.txt')==old_key and f.state()['active']; done('failed reconfigure restores existing install and active service')
unrelated=f.root/'var/lib/unrelated'; unrelated.write_text('keep')
f.run('--uninstall','УДАЛИТЬ\n')
for path in ['etc/openflux','var/lib/openflux','var/log/openflux','var/backups/openflux-rublev','etc/systemd/system/openflux.service','etc/logrotate.d/openflux','usr/local/bin/openflux','usr/local/sbin/openflux-setup']:
    assert not f.exists(path),path
assert unrelated.read_text()=='keep' and not f.state()['user'] and not f.state()['group']; done('full uninstall: owned files/account removed, unrelated file survives')
f.run('--uninstall'); done('repeat uninstall is harmless')
g=Fixture(); g.run('--install',url+'\n',expected=1,FAIL_START='1')
assert not g.exists('etc/openflux') and not g.exists('usr/local/bin/openflux') and not g.state()['user']; done('fresh install startup failure rolls back')
h=Fixture(); (h.root/'usr/local/bin/openflux').write_text('foreign')
h.run('--install',url+'\n',expected=1); h.run('--uninstall','УДАЛИТЬ\n',expected=1)
assert h.read('usr/local/bin/openflux')==b'foreign'; done('foreign installation protected from install and uninstall')
j=Fixture(); j.run('--install','https://evil.example/test\n'+url+'\n',MOCK_ARCH='aarch64'); j.verify_profile('yandex',url)
assert 'openflux-linux-arm64' in (j.root/'calls.log').read_text(); done('arm64 selected; invalid URL rejected')
k=Fixture(); k.run('--install',url+'\n0\n',EDITOR_KIND='unknown'); assert not k.exists('etc/openflux'); done('unknown editor can be cancelled before install')
l=Fixture(); l.run('--install',url+'\n',expected=1,EDITOR_KIND='readonly'); assert not l.exists('etc/openflux'); done('read-only document rejected')
m=Fixture(); m.run('--install',url+'\n2\n',EDITOR_KIND='unknown'); m.verify_profile('vyandex',url); done('manual editor selection works')
n=Fixture(); n.run('--install',url+'\n',CLIENT_MODE='2'); n.verify_profile('yandex',url,'ios'); done('iPhone mode from interactive menu is installed consistently')
n_key=n.read('etc/openflux/secret.txt')
n.run('--install',url+'\n',CLIENT_MODE='1'); n.verify_profile('yandex',url)
assert n.read('etc/openflux/secret.txt')==n_key; done('switch iPhone to session preserves key')
n.run('--install-ios',url2+'\n',EDITOR_KIND='vyandex'); n.verify_profile('vyandex',url2,'ios')
assert n.read('etc/openflux/secret.txt')==n_key; done('install-ios selects iPhone mode and preserves key')
result=n.run('--key'); assert result.stdout.encode()==n_key; done('key command prints only the existing key')
config_before=n.read('etc/openflux/server.conf')
(n.root/'etc/openflux/secret.txt').write_text('broken')
n.run('--install-ios',url+'\n',expected=1)
assert n.read('etc/openflux/secret.txt')==b'broken' and n.read('etc/openflux/server.conf')==config_before and n.state()['active']; done('invalid key aborts before modifying installed service')
(ROOT/'test-summary-v1_1.txt').write_text('\n'.join(passed)+'\n')
print(str(len(passed))+' scenarios passed; real system/network operations were mocked.')

for mode in ('ios', 'session'):
    for editor in ('yandex', 'vyandex'):
        f = Fixture()
        f.run('--install', url+'\n', CLIENT_MODE='2' if mode == 'ios' else '1', EDITOR_KIND=editor)
        cfg = f.root/'etc/openflux/server.conf'
        cfg.write_text(cfg.read_text() + 'Debug = 0\n')
        cookies = f.root/'var/lib/openflux/cookies.json'
        cookie_bytes = b'{"https://disk.yandex.ru/i/Testing_123": {"fixture": "cookie"}}\n'
        cookies.write_bytes(cookie_bytes)
        cookies.chmod(0o600)
        old_conf, old_key = cfg.read_bytes(), f.read('etc/openflux/secret.txt')
        (f.root/'usr/local/bin/openflux').write_bytes(b'old-binary-fixture')
        before = (f.root/'calls.log').read_text()
        f.run('--update')
        f.verify_profile(editor, url, mode)
        assert cfg.read_bytes() == old_conf and f.read('etc/openflux/secret.txt') == old_key
        assert cookies.read_bytes() == cookie_bytes
        after = (f.root/'calls.log').read_text()[len(before):]
        assert 'document.html' not in after, 'update must not re-detect or change editor'
        backups = list((f.root/'var/backups/openflux-rublev').glob('snapshot.*'))
        assert len(backups) == 1 and backups[0].stat().st_mode & 0o777 == 0o700
        assert (backups[0]/'config/secret.txt').read_bytes() == old_key
        assert (backups[0]/'state/cookies.json').read_bytes() == cookie_bytes
        assert any(p.is_file() and p.read_bytes() == b'old-binary-fixture' for p in backups[0].iterdir())
        f.run('--update', expected=1, FAIL_RUNTIME='restart')
        assert cookies.read_bytes() == cookie_bytes and cfg.read_bytes() == old_conf
        assert f.read('etc/openflux/secret.txt') == old_key and f.state()['active']
        f.run('--update', expected=1, DROP_INS='custom.conf')
        f.run('--uninstall', 'УДАЛИТЬ\n')
        assert not f.exists('var/backups/openflux-rublev')
        done('update/backup/restart rollback/cookie preservation/uninstall: '+mode+'/'+editor)

f = Fixture()
p = f.run('--install-ios', url+'\n', expected=2, FAIL_RUNTIME='captcha')
assert f.exists('etc/openflux/secret.txt') and not f.state()['active']
assert 'Выход в интернет не готов' in p.stdout and 'CAPTCHA.md' in p.stdout
f.run('--update')
assert f.state()['active']
done('server captcha keeps a recoverable installation, stops retries and returns 2')

f = Fixture(); f.run('--update', expected=1)
assert not f.exists('etc/openflux')
done('update of absent installation does not create or install anything')
print(str(len(passed))+' lifecycle scenarios passed; OS/network operations were mocked.')
