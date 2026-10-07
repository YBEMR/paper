function out=s55_method(tr,method,inject)
% Each invocation creates its own candidate space. No reference argument.
c=tr.case;h=tr.thermal;b=struct('timer',tic,'limit',c.budget_s);
if nargin>2
    if isstruct(inject),b.inject_phase=inject.phase;b.inject_error=inject.identifier;
    else,b.inject_phase=inject;end
end
out=struct('method',method,'status','running','message','','schedule',s55_schedule(c), ...
    'enumeration_complete',false,'sort_complete',false,'library_count',0,'visited',0, ...
    'lower_J',NaN,'upper_J',Inf,'observed_noheat_upper_J',Inf,'noheat_optimum_J',NaN, ...
    'noheat_optimal_configs',zeros(0,c.n),'optimal_configs',zeros(0,c.n), ...
    'optimal_value_proved',false,'optimal_set_complete',false,'proof_scope','not_proved', ...
    'attempts',{{}},'thermal_calls',0,'representative_count',0,'reference',struct(), ...
    'elapsed_s',0,'input_id',c.id,'noheat_diagnostic',struct());
lib=[];
try
    lib=s55_enumerate(c,b);out.library_count=lib.count;out.visited=lib.visited;
    out.lower_J=lib.lower_J;out.observed_noheat_upper_J=lib.observed_upper_J;
    out.enumeration_complete=lib.complete;
    if ~lib.complete,out.status=lib.status;out.message=lib.message;finish();return;end
    if lib.count==0
        out.status='noheat_infeasible';out.lower_J=Inf;out.upper_J=Inf;
        out.proof_scope=lib.proof;if isempty(out.proof_scope),out.proof_scope='complete_noheat_enumeration';end
        finish();return;
    end
    lib=s55_sort(c,lib,b);out.sort_complete=true;
    out.noheat_optimum_J=min(lib.energy);out.lower_J=out.noheat_optimum_J;
    out.noheat_optimal_configs=unique(lib.rows(lib.rank==1,1:c.n),'rows');
    s55_budget(b,'sort');
    if strcmp(method,'joint_noheat')
        out.schedule=s55_schedule(c,lib.rows(1,:));out.upper_J=out.noheat_optimum_J;
        out.optimal_value_proved=true;out.optimal_set_complete=true;
        out.optimal_configs=out.noheat_optimal_configs;out.proof_scope='noheat_only_energy_tolerance';
        out.status='complete_noheat';
        % Thermal diagnosis is not a proof that every no-heat optimum is safe.
        out.noheat_diagnostic=s55_thermal(c,out.schedule,h,[],b);out.thermal_calls=1;
    elseif strcmp(method,'full_suffix')
        actions=lib.rows(:,1:c.n).*uint16(lib.rows(:,c.n+1:end)==0);
        [~,first]=unique(actions,'rows','stable');s55_budget(b,'selection');
        out.representative_count=numel(first);uncertain=false;out.status='no_safe_representative';
        net=thv_build(h);
        for k=first'
            s55_budget(b,'selection');s=s55_schedule(c,lib.rows(k,:));z=s55_thermal(c,s,h,net,b);
            s55_budget(b,'selection');out.thermal_calls=out.thermal_calls+1;
            out.attempts{end+1}=struct('action_key',actions(k,:), ...
                'start_stage_ids',{c.stage_id(s.start==0)},'row',lib.rows(k,:), ...
                'energy_J',lib.energy(k),'completion_s',lib.completion(k,:), ...
                'thermal_status',z.status,'peak_C',z.peak);
            if strcmp(z.status,'safe')
                out.schedule=s;out.upper_J=lib.energy(k);out.status='complete_safe';break;
            end
            uncertain=uncertain || strcmp(z.status,'unresolved');
        end
        if uncertain && ~strcmp(out.status,'complete_safe'),out.status='thermal_unresolved';end
    elseif strcmp(method,'thermal_reference')
        [configs,first,cid]=unique(lib.rows(:,1:c.n),'rows','stable');s55_budget(b,'selection');
        nc=size(configs,1);total=accumarray(cid,1,[nc 1]);counts=zeros(nc,1);
        state=zeros(nc,1);unresolved=false(nc,1);energy=lib.energy(first);ranks=lib.rank(first);
        witness=zeros(nc,2*c.n,'uint16');peaks=nan(nc,2);net=thv_build(h);bestRank=Inf;
        out.reference=struct('configs',configs,'energy_J',energy,'rank',ranks,'total_schedules',total, ...
            'evaluated',counts,'state',state,'has_unresolved',unresolved,'witness_rows',witness,'peak_C',peaks, ...
            'state_legend','0=unchecked,1=safe_witness,2=all_excluded,3=unresolved');
        for k=1:lib.count
            s55_budget(b,'selection');
            if lib.rank(k)>bestRank,break;end
            id=cid(k);if state(id)==1,continue;end
            z=s55_thermal(c,s55_schedule(c,lib.rows(k,:)),h,net,b);s55_budget(b,'selection');
            counts(id)=counts(id)+1;out.thermal_calls=out.thermal_calls+1;
            if strcmp(z.status,'safe')
                state(id)=1;witness(id,:)=lib.rows(k,:);peaks(id,:)=z.peak;bestRank=min(bestRank,lib.rank(k));
                if lib.energy(k)<out.upper_J,out.upper_J=lib.energy(k);out.schedule=s55_schedule(c,lib.rows(k,:));end
            elseif strcmp(z.status,'unresolved'),unresolved(id)=true;state(id)=3;
            elseif counts(id)==total(id) && ~unresolved(id),state(id)=2;end
            out.reference.evaluated=counts;out.reference.state=state;out.reference.has_unresolved=unresolved;
            out.reference.witness_rows=witness;out.reference.peak_C=peaks;
        end
        s55_budget(b,'selection');out.status='reference_finished';
    else,error('s55:method','Unknown method');end
catch err
    if strcmp(err.identifier,'s55:timeout'),out.status='timeout';
    elseif strcmp(err.identifier,'s55:resource') || strcmp(err.identifier,'s55:io') || contains(lower(err.identifier),'nomem') || contains(lower(err.message),'out of memory'),out.status='resource_unresolved';
    else,out.status='error';end
    out.message=getReport(err,'extended','hyperlinks','off');
end
if strcmp(method,'thermal_reference') && isfield(out.reference,'state')
    rr=out.reference;possible=rr.state~=2;safe=rr.state==1;
    if any(possible),out.lower_J=min(rr.energy_J(possible));else,out.lower_J=Inf;end
    if any(safe)
        out.upper_J=min(rr.energy_J(safe));
        out.optimal_value_proved=out.upper_J-out.lower_J<=tol(out.upper_J,out.lower_J);
        best=min(rr.rank(safe));layer=rr.rank==best;
        if out.optimal_value_proved
            out.optimal_configs=rr.configs(safe & layer,:);
            out.optimal_set_complete=all(ismember(rr.state(rr.rank<=best),[1 2]));
            out.proof_scope='same_start_grid_energy_tolerance';
        end
    elseif all(rr.state==2)
        out.status='grid_thermal_infeasible';out.proof_scope='complete_configuration_exclusion';
    end
end
finish();
    function t=tol(a,z),t=max(c.energy_abs_tol,c.energy_rel_tol*max(abs([a z])));end
    function finish(),out.elapsed_s=toc(b.timer);end
end
