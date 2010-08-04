# bash completion for yum-utils

# repomanage
_yu_repomanage()
{
    COMPREPLY=()

    case "$3" in
        -h|--help)
            return 0
            ;;
        -k|--keep)
            COMPREPLY=( $( compgen -W '1 2 3 4 5 6 7 8 9' -- "$2" ) )
            return 0
            ;;
    esac

    if [[ "$2" == -* ]] ; then
        COMPREPLY=( $( compgen -W '--old --new --space --keep --nocheck
            --help' -- "$2" ) )
        return 0
    fi

    COMPREPLY=( $( compgen -d -- "$2" ) )
} &&
complete -F _yu_repomanage -o filenames repomanage repomanage.py

# package-cleanup
_yu_package_cleanup()
{
    COMPREPLY=()

    case "$3" in
        -h|--help|--leaf-regex|--qf|--queryformat)
            return 0
            ;;
        --count)
            COMPREPLY=( $( compgen -W '1 2 3 4 5 6 7 8 9' -- "$2" ) )
            return 0
            ;;
        -c)
            COMPREPLY=( $( compgen -f -o plusdirs -X "!*.conf" -- "$2" ) )
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--help --problems --leaves --all --leaf-regex
        --exclude-devel --exclude-bin --orphans --noplugins --quiet -y --dupes
        --cleandupes --oldkernels --count --keepdevel -c --queryformat' \
            -- "$2" ) )
} &&
complete -F _yu_package_cleanup -o filenames package-cleanup package-cleanup.py

# verifytree
_yu_verifytree()
{
    COMPREPLY=()

    case "$3" in
        -h|--help|-t|--testopia)
            return 0
            ;;
    esac

    if [[ "$2" == -* ]] ; then
        COMPREPLY=( $( compgen -W '--help --checkall --testopia --treeinfo' \
            -- "$2" ) )
        return 0
    fi

    COMPREPLY=( $( compgen -d -- "$2" ) )
} &&
complete -F _yu_verifytree -o filenames verifytree verifytree.py

# repo-graph
_yu_repo_graph()
{
    COMPREPLY=()

    case "$3" in
        -h|--help)
            return 0
            ;;
        --repoid)
            type _yum_repolist &>/dev/null && _yum_repolist all "$2"
            return 0
            ;;
        -c)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.conf' -- "$2" ) )
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--help --repoid -c' -- "$2" ) )
} &&
complete -F _yu_repo_graph -o filenames repo-graph repo-graph.py

# repo-rss
_yu_repo_rss()
{
    COMPREPLY=()

    case "$3" in
        -h|--help|-l|-t|-d|-r|-a)
            return 0
            ;;
        -f)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.xml' -- "$2" ) )
            return 0
            ;;
        -c)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.conf' -- "$2" ) )
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--help -f -l -t -d -r --tempcache -g -a -c' \
        -- "$2" ) )
    [[ "$2" == -* ]] && return 0
    type _yum_repolist &>/dev/null && _yum_repolist all "$2"
} &&
complete -F _yu_repo_rss -o filenames repo-rss repo-rss.py

# repoclosure
_yu_repoclosure()
{
    COMPREPLY=()

    case "$3" in
        -h|--help|-a|--arch|--basearch|--repofrompath)
            return 0
            ;;
        -c|--config)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.conf' -- "$2" ) )
            return 0
            ;;
        -l|--lookaside|-r|--repoid)
            type _yum_repolist &>/dev/null && _yum_repolist all "$2"
            return 0
            ;;
        -p|--pkg)
            type _yum_list &>/dev/null && _yum_list all "$2"
            return 0
            ;;
        -g|--group)
            type _yum_grouplist &>/dev/null && _yum_grouplist "" "$2"
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--help --config --arch --basearch --builddeps
        --lookaside --repoid --tempcache --quiet --newest --repofrompath --pkg
        --group' -- "$2" ) )
} &&
complete -F _yu_repoclosure -o filenames repoclosure repoclosure.py

# repoquery
_yu_repoquery()
{
    COMPREPLY=()

    local groupmode=false
    for (( i=0; i < ${#COMP_WORDS[@]}-1; i++ )) ; do
        case "${COMP_WORDS[i]}" in -g|--group) groupmode=true ; break ;; esac
    done

    case "$3" in
        -h|--help|--version|-f|--file|--qf|--queryformat|--resolve|--archlist|\
        --whatprovides|--whatrequires|--whatobsoletes|--whatconflicts|\
        --repofrompath)
            return 0
            ;;
        -l|--list|-i|--info|-R|--requires)
            if $groupmode ; then
                type _yum_grouplist &>/dev/null && _yum_grouplist "" "$2"
            else
                type _yum_list &>/dev/null && _yum_list all "$2"
            fi
            return 0
            ;;
        --provides|--obsoletes|--conflicts|--groupmember|--changelog|\
        --location|--nevra|--envra|--nvr|-s|--source)
            type _yum_list &>/dev/null && _yum_list all "$2"
            return 0
            ;;
        --grouppkgs)
            COMPREPLY=( $( compgen -W 'all default optional mandatory' \
                -- "$2" ) )
            return 0
            ;;
        --pkgnarrow)
            COMPREPLY=( $( compgen -W 'all available updates installed extras
                obsoletes recent repos' -- "$2" ) )
            return 0
            ;;
        --repoid)
            type _yum_repolist &>/dev/null && _yum_repolist all "$2"
            return 0
            ;;
        --enablerepo)
            type _yum_repolist &>/dev/null && _yum_repolist disabled "$2"
            return 0
            ;;
        --disablerepo)
            type _yum_repolist &>/dev/null && _yum_repolist enabled "$2"
            return 0
            ;;
        -c)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.conf' -- "$2" ) )
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--version --help --list --info --file
        --queryformat --groupmember --all --requires --provides --obsoletes
        --conflicts --changelog --location --nevra --envra --nvr --source
        --srpm --resolve --exactdeps --recursive --whatprovides --whatrequires
        --whatobsoletes --whatconflicts --group --grouppkgs --archlist
        --pkgnarrow --installed --show-duplicates --repoid --enablerepo
        --disablerepo --repofrompath --plugins --quiet --verbose --cache
        --tempcache --querytags --config --tree-requires --tree-conflicts
        --tree-obsoletes --tree-whatrequires' -- "$2" ) )
} &&
complete -F _yu_repoquery -o filenames repoquery repoquery.py

# yumdb
_yu_yumdb()
{
    COMPREPLY=()

    case "$3" in
        -h|--help|-version)
            return 0
            ;;
        -c|--config)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.conf' -- "$2" ) )
            return 0
            ;;
        shell)
            COMPREPLY=( $( compgen -f -o plusdirs -- "$2" ) )
            return 0
            ;;
    esac

    if [ $COMP_CWORD -le 1 ] ; then
        COMPREPLY=( $( compgen -W 'get set del rename rename-force copy search
            exist unset info shell --version --help --noplugins --config' \
                -- "$2" ) )
    fi
} &&
complete -F _yu_yumdb -o filenames yumdb yumdb.py

# repodiff
_yu_repodiff()
{
    COMPREPLY=()

    case "$3" in
        -h|--help|--version|-n|--new|-o|--old|-a|--archlist)
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--version --help --new --old --quiet --archlist
        --size --simple' -- "$2" ) )
} &&
complete -F _yu_repodiff repodiff repodiff.py

# Local variables:
# mode: shell-script
# sh-basic-offset: 4
# sh-indent-comment: t
# indent-tabs-mode: nil
# End:
# ex: ts=4 sw=4 et filetype=sh
