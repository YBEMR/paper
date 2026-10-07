function a=s40_append(a,b)
if isempty(a), a=b; else, a(end+1)=b; end
end
