function entries=c44_audit(paths)
entries=struct('path',{},'sha256',{});
for j=1:numel(paths)
    p=paths{j}; fid=fopen(p,'rb'); assert(fid>=0,p); guard=onCleanup(@()fclose(fid));
    bytes=fread(fid,inf,'*uint8'); clear guard;
    md=java.security.MessageDigest.getInstance('SHA-256'); md.update(bytes);
    hash=typecast(md.digest(),'uint8'); hex=upper(reshape(dec2hex(hash,2)',1,[]));
    entries(end+1)=struct('path',p,'sha256',hex); %#ok<AGROW>
end
end
