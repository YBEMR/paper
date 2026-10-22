function [packet, meta] = htp_load_a03(input_path)
%HTP_LOAD_A03 Read the exact-decimal frozen packet into MATLAB doubles.
% Source-file identity is checked; this is not a continuous safety checker.
root=fileparts(fileparts(mfilename('fullpath')));
if nargin<1, input_path=fullfile(root,'inputs','a03_minimal_v1.json'); end
manifest=jsondecode(fileread(fullfile(root,'inputs','a03_manifest.json')));
fid=fopen(input_path,'rb'); assert(fid~=-1,'htp:A03Missing','Cannot read input.');
closer=onCleanup(@() fclose(fid)); bytes=fread(fid,Inf,'*uint8');
digest=java.security.MessageDigest.getInstance('SHA-256'); digest.update(bytes);
actual=lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
assert(strcmp(actual,manifest.input_sha256),'htp:A03HashMismatch','Input differs from the frozen packet.');
packet=jsondecode(native2unicode(bytes(:)','UTF-8')); % Parse the same bytes that were hashed.
assert(strcmp(packet.schema,'htp.a03.v1'),'htp:A03Schema','Unsupported schema.');
assert(strcmp(packet.execution.start_domain,'CONTINUOUS_NONNEGATIVE'),'htp:A03StartDomain','Unexpected start domain.');
assert(numel(packet.mode_table)==36 && numel(packet.thermal.node_order)==5,'htp:A03Shape','Unexpected mode/node count.');
meta=struct('input_sha256',actual,'numeric_representation','MATLAB double; source JSON decimals remain authoritative', ...
    'safety_status','UNASSESSED','research_calls',0);
end
