"""Create the NEW native adapter from the unchanged, consumed C_noheur source."""
from pathlib import Path
root=Path(__file__).resolve().parent
s=(root/'mechanism_trials_v1/native_none/solve_model.m').read_text(encoding='utf-8')
s=s.replace("    streamEvents = false; eventNumber = 0;", """    streamEvents = false; eventNumber = 0;
    observation=struct('protocol','D279-public-observer-v1','history_limit',100000, ...
        'anchors',{{}},'callback_spans',[],'profile_started',false,'profile_archived',false);
    profileActive=false;""")
s=s.replace("        opts = optimoptions('intlinprog','Display','off', ...", """        % Public R2023b interface only; no internal/protected profiler APIs.
        observerClock=tic;
        profile('clear');
        profile('on','-timestamp','-historysize','100000','-timer','performance');
        profileActive=true;
        observation.profile_started=true;
        observation.profile_status=profile('status');
        st=observation.profile_status;
        if ~strcmp(st.ProfilerStatus,'on') || ~strcmp(st.HistoryTracking,'timestamp') ...
                || ~strcmp(st.Timer,'performance') || st.HistorySize~=100000 ...
                || ~strcmp(st.DetailLevel,'mmex')
            error('D279:profileStatus','Unexpected public Profiler settings; no fallback');
        end
        observation.profile_setup_s=toc(observerClock);
        opts = optimoptions('intlinprog','Display','iter', ...""")
s=s.replace("            phaseClock=tic;\n            lastwarn('');", """            observation.anchors{end+1}=mark('begin');
            fprintf('D279_NATIVE_BEGIN\\n');
            phaseClock=tic;
            lastwarn('');""")
s=s.replace("            result.phase_seconds.intlinprog_call=toc(phaseClock);", """            result.phase_seconds.intlinprog_call=toc(phaseClock);
            observation.anchors{end+1}=mark('end');
            fprintf('D279_NATIVE_END\\n');""")
s=s.replace("    result.callbacks=callbacks;", """    % One final public snapshot. profile('info') stops recording: never use
    % it in a callback or to obtain mid-solve progress.
    if profileActive
        observerClock=tic;
        try
            profileData=profile('info');
            profileActive=false;
            observation.profile_status_after=profile('status');
            observation.history_events=size(profileData.FunctionHistory,2);
            observation.history_capacity_reached=observation.history_events>=100000;
            observation.profile_snapshot_s=toc(observerClock);
            observerClock=tic;
            save([prefix '.profile.mat'],'profileData','-v7');
            observation.profile_archive_s=toc(observerClock);
            observation.profile_archived=true;
        catch observerError
            profile('off');
            observation.error=getReport(observerError,'extended','hyperlinks','off');
        end
    end
    result.observation=observation;
    result.callbacks=callbacks;""")
s=s.replace("    requestNumber=requestNumber+1;", "    return; % Exactly one request in this independent observation worker.")
s=s.replace("    function stop = callback(x,values,state)\n        stop = false;", """    function stop = callback(x,values,state)
        callbackStart=toc(requestClock);
        stop = false;""")
s=s.replace("            callbackFields=union(callbackFields,fieldnames(values));", """            if isfield(values,'phase') && strcmp(values.phase,'rootlp')
                observation.anchors{end+1}=mark('root');
            end
            callbackFields=union(callbackFields,fieldnames(values));""")
s=s.replace("            stop=true;\n        end\n    end", """            stop=true;
        end
        observation.callback_spans(end+1,:)=[callbackStart,toc(requestClock)];
    end

    function anchor=mark(label)
        before=toc(requestClock);
        switch label
            case 'begin', measured=d279_begin_marker(requestClock);
            case 'root', measured=d279_root_marker(requestClock);
            case 'end', measured=d279_end_marker(requestClock);
        end
        after=toc(requestClock);
        anchor=struct('label',label,'before_s',before,'inside_s',measured,'after_s',after);
    end""")
s+='''
function t=d279_begin_marker(clock)
t=toc(clock);
end
function t=d279_root_marker(clock)
t=toc(clock);
end
function t=d279_end_marker(clock)
t=toc(clock);
end
'''
p=root/'root_tail_observer_v1/native/solve_model.m'
p.write_text(s,encoding='utf-8',newline='\n')
print(p)
