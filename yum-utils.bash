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
complete -F _yu_repomanage -o filenames repomanage

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
complete -F _yu_package_cleanup -o filenames package-cleanup

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
complete -F _yu_verifytree -o filenames verifytree

# Local variables:
# mode: shell-script
# sh-basic-offset: 4
# sh-indent-comment: t
# indent-tabs-mode: nil
# End:
# ex: ts=4 sw=4 et filetype=sh
