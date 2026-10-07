function entries=s40_manifest(folder)
files=dir(fullfile(folder,'**','*')); entries=struct([]);
for k=1:numel(files)
    if files(k).isdir, continue; end
    path=fullfile(files(k).folder,files(k).name);
    if endsWith(path,'manifest.json')||endsWith(path,'console.txt'), continue; end
    fid=fopen(path,'rb'); assert(fid>=0); bytes=fread(fid,inf,'*uint8'); fclose(fid);
    md=java.security.MessageDigest.getInstance('SHA-256'); md.update(bytes);
    hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[]));
    entries(end+1)=struct('path',strrep(path,[folder filesep],''),'sha256',hash,'bytes',numel(bytes)); %#ok<AGROW>
end
end
