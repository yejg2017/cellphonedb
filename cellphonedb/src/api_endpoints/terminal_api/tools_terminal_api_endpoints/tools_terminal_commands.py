import os
import urllib.parse
from typing import Optional, List

import click
import pandas as pd

from cellphonedb.src.app.app_logger import app_logger
from cellphonedb.src.app.cellphonedb_app import output_dir, data_dir
from cellphonedb.src.core.generators.gene_generator import gene_generator
from cellphonedb.src.exceptions.MissingRequiredColumns import MissingRequiredColumns
from cellphonedb.src.local_launchers.local_collector_launcher import LocalCollectorLauncher
from cellphonedb.tools.generate_data.filters.non_complex_interactions import only_noncomplex_interactions
from cellphonedb.tools.generate_data.filters.remove_interactions import remove_interactions_in_file
from cellphonedb.tools.generate_data.getters import get_iuphar_guidetopharmacology
from cellphonedb.tools.generate_data.mergers.add_curated import add_curated
from cellphonedb.tools.generate_data.mergers.merge_interactions import merge_iuphar_imex_interactions
from cellphonedb.tools.generate_data.parsers import parse_iuphar_guidetopharmacology
from cellphonedb.tools.generate_data.parsers.parse_interactions_imex import parse_interactions_imex
from cellphonedb.utils import utils
from cellphonedb.utils.utils import _get_separator, read_data_table_from_file, write_to_file


@click.command()
@click.option('--user-gene', type=click.File('r'), default=None)
@click.option('--fetch-uniprot', is_flag=True)
@click.option('--fetch-ensembl', is_flag=True)
@click.option('--result-path', type=str, default=None)
@click.option('--log-file', type=str, default='log.txt')
def generate_genes(user_gene: Optional[click.File],
                   fetch_uniprot: bool,
                   fetch_ensembl: bool,
                   result_path: str,
                   log_file: str) -> None:
    output_path = _set_paths(output_dir, result_path)

    # TODO: Add logger
    if fetch_ensembl:
        print('fetching remote ensembl data ... ', end='')
        source_url = 'http://www.ensembl.org/biomart/martservice?query={}'
        query = '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE Query><Query virtualSchemaName = "default" ' \
                'formatter = "CSV" header = "1" uniqueRows = "1" count = "" datasetConfigVersion = "0.6" >' \
                '<Dataset name = "hsapiens_gene_ensembl" interface = "default" >' \
                '<Attribute name = "ensembl_gene_id" />' \
                '<Attribute name = "ensembl_transcript_id" />' \
                '<Attribute name = "external_gene_name" />' \
                '<Attribute name = "hgnc_symbol" />' \
                '<Attribute name = "uniprotswissprot" />' \
                '</Dataset>' \
                '</Query>'

        url = source_url.format(urllib.parse.quote(query))
        ensembl_db: pd.DataFrame = pd.read_csv(url)
        print('done')
    else:
        ensembl_db: pd.DataFrame = read_data_table_from_file(os.path.join(data_dir, 'sources/ensembl.txt'))
        print('read local ensembl file')

    # additional data comes from given file or uniprot remote url
    if fetch_uniprot:
        print('fetching remote uniprot file ... ', end='')
        source_url = 'https://www.uniprot.org/uniprot/?query=*&format=tab&force=true' \
                     '&columns=id,entry%20name,reviewed,protein%20names,genes,organism,length' \
                     '&fil=organism:%22Homo%20sapiens%20(Human)%20[9606]%22%20AND%20reviewed:yes' \
                     '&compress=yes'

        uniprot_db = pd.read_csv(source_url, sep='\t', compression='gzip')
        print('done')
    else:
        uniprot_db: pd.DataFrame = read_data_table_from_file(os.path.join(data_dir, 'sources/uniprot.tab'))
        print('read local uniprot file')

    ensembl_columns = {
        'Gene name': 'gene_name',
        'Gene stable ID': 'ensembl',
        'HGNC symbol': 'hgnc_symbol',
        'UniProtKB/Swiss-Prot ID': 'uniprot_ensembl'
    }

    uniprot_columns = {
        'Entry': 'uniprot',
        'Gene names': 'gene_names'
    }

    result_columns = [
        'gene_name',
        'uniprot',
        'hgnc_symbol',
        'ensembl'
    ]

    ensembl_db = ensembl_db[list(ensembl_columns.keys())].rename(columns=ensembl_columns)
    uniprot_db = uniprot_db[list(uniprot_columns.keys())].rename(columns=uniprot_columns)
    hla_genes = read_data_table_from_file(os.path.join(data_dir, 'sources/hla_genes.csv'))
    cpdb_interactions = pd.read_csv('cellphonedb/src/core/data/interaction_input.csv')
    if user_gene:
        separator = _get_separator(os.path.splitext(user_gene.name)[-1])
        user_gene: pd.DataFrame = pd.read_csv(user_gene, sep=separator)

    cpdb_genes = gene_generator(ensembl_db, uniprot_db, hla_genes, user_gene, cpdb_interactions, result_columns)

    cpdb_genes[result_columns].to_csv('{}/{}'.format(output_path, 'gene_input.csv'), index=False)


@click.command()
@click.argument('imex_raw_filename')
@click.argument('iuphar_raw_filename')
@click.argument('database_proteins_filename', default='protein.csv')
@click.argument('database_gene_filename', default='gene.csv')
@click.argument('database_complex_filename', default='complex.csv')
@click.argument('interaction_to_remove_filename')
@click.argument('interaction_curated_filename')
@click.option('--result_path', default='')
def generate_interactions(
        imex_raw_filename: str,
        iuphar_raw_filename: str,
        database_proteins_filename: str,
        database_gene_filename: str,
        database_complex_filename: str,
        interaction_to_remove_filename: str,
        interaction_curated_filename: str,
        result_path: str,
) -> None:
    interactions_base = utils.read_data_table_from_file(imex_raw_filename, na_values='-')
    proteins = pd.read_csv(database_proteins_filename)
    genes = pd.read_csv(database_gene_filename)
    complexes = pd.read_csv(database_complex_filename)
    interactions_to_remove = pd.read_csv(interaction_to_remove_filename)
    interaction_curated = pd.read_csv(interaction_curated_filename)

    print('generating imex file')
    imex_interactions = parse_interactions_imex(interactions_base, proteins, genes)

    output_path = _set_paths(output_dir, result_path)
    download_path = _set_paths(output_path, 'downloads')

    print('Getting Iuphar interactions')
    iuphar_original = get_iuphar_guidetopharmacology.call(iuphar_raw_filename,
                                                          download_path,
                                                          default_download_response='no',
                                                          )

    print('generating iuphar file')
    iuphar_interactions = parse_iuphar_guidetopharmacology.call(iuphar_original, genes, proteins)

    print('merging iuphar/imex')
    merged_interactions = merge_iuphar_imex_interactions(iuphar_interactions, imex_interactions)

    print('removing complex interactions')
    no_complex_interactions = only_noncomplex_interactions(merged_interactions, complexes)

    print('removing selected interactions')
    clean_interactions = remove_interactions_in_file(no_complex_interactions, interactions_to_remove)

    print('adding curated interaction')
    interactions_with_curated = add_curated(clean_interactions, interaction_curated)

    interactions_with_curated[['partner_a', 'partner_b', 'source', 'comments_interaction']].to_csv(
        '{}/interaction_input.csv'.format(output_path), index=False)


@click.command()
@click.option('--user-protein', type=click.File('r'), default=None)
@click.option('--fetch-uniprot', is_flag=True)
@click.option('--result-path', type=str, default=None)
@click.option('--log-file', type=str, default='log.txt')
def generate_proteins(user_protein: Optional[click.File],
                      fetch_uniprot: bool,
                      result_path: str,
                      log_file: str):
    # additional data comes from given file or uniprot remote url
    if fetch_uniprot:
        source_url = 'https://www.uniprot.org/uniprot/?query=*&format=tab&force=true' \
                     '&columns=id,entry%20name,reviewed,protein%20names,genes,organism,length' \
                     '&fil=organism:%22Homo%20sapiens%20(Human)%20[9606]%22%20AND%20reviewed:yes' \
                     '&compress=yes'

        additional_df = pd.read_csv(source_url, sep='\t', compression='gzip')
        print('read remote uniprot file')
    else:
        additional_df = pd.read_csv(os.path.join(data_dir, 'sources/uniprot.tab'), sep='\t')
        print('read local uniprot file')

    curated_df: pd.DataFrame = pd.read_csv(os.path.join(data_dir, 'sources/protein_curated.csv'))

    output_path = _set_paths(output_dir, result_path)
    log_path = '{}/{}'.format(output_path, log_file)
    result = _merge_proteins(curated_df, additional_df, log_path)

    if user_protein:
        separator = _get_separator(os.path.splitext(user_protein.name)[-1])
        user_df: pd.DataFrame = pd.read_csv(user_protein, sep=separator)

        result = _merge_proteins(user_df, result, log_path)

    result.to_csv('{}/{}'.format(output_path, 'protein_input.csv'), index=False)


@click.command()
@click.option('--user-complex', type=click.File('r'), default=None)
@click.option('--result-path', type=str, default=None)
@click.option('--log-file', type=str, default='log.txt')
def generate_complex(user_complex: Optional[click.File], result_path: str, log_file: str):
    result: pd.DataFrame = pd.read_csv(os.path.join(data_dir, 'sources/complex_curated.csv'))

    output_path = _set_paths(output_dir, result_path)
    log_path = '{}/{}'.format(output_path, log_file)

    if user_complex:
        separator = _get_separator(os.path.splitext(user_complex.name)[-1])
        user_df: pd.DataFrame = pd.read_csv(user_complex, sep=separator)
        try:
            result = _merge_complex(user_df, result, log_path)
        except MissingRequiredColumns as e:
            app_logger.error(e)

    result.to_csv('{}/{}'.format(output_path, 'complex_input.csv'), index=False)


@click.command()
@click.option('--input-path', type=str, default=data_dir)
@click.option('--result-path', type=str, default='filtered')
def filter_all(input_path, result_path):
    interactions: pd.DataFrame = pd.read_csv(os.path.join(input_path, 'interaction_input.csv'))
    complexes: pd.DataFrame = pd.read_csv(os.path.join(input_path, 'complex_input.csv'))
    proteins: pd.DataFrame = pd.read_csv(os.path.join(input_path, 'protein_input.csv'))
    genes: pd.DataFrame = pd.read_csv(os.path.join(input_path, 'gene_input.csv'))
    output_path = _set_paths(output_dir, result_path)

    interacting_partners = pd.concat([interactions['partner_a'], interactions['partner_b']]).drop_duplicates()

    filtered_complexes = _filter_complexes(complexes, interacting_partners)
    write_to_file(filtered_complexes, 'complex_input.csv', output_path=output_path)

    filtered_proteins, interacting_proteins = _filter_proteins(proteins, filtered_complexes, interacting_partners)
    write_to_file(filtered_proteins, 'protein_input.csv', output_path=output_path)

    filtered_genes = _filter_genes(genes, interacting_proteins)
    write_to_file(filtered_genes, 'gene_input.csv', output_path=output_path)

    rejected_members = interacting_partners[~(interacting_partners.isin(filtered_complexes['complex_name']) |
                                              interacting_partners.isin(filtered_proteins['uniprot']))]

    if len(rejected_members):
        app_logger.warning('There are some proteins or complexes not interacting properly: `{}`'.format(
            ', '.join(rejected_members)))


@click.command()
@click.argument('table')
@click.argument('file', default='')
def collect(table, file):
    getattr(LocalCollectorLauncher(), table)(file)


def _filter_genes(genes: pd.DataFrame, interacting_proteins: pd.DataFrame) -> pd.DataFrame:
    filtered_genes = genes[genes['uniprot'].isin(interacting_proteins)]

    return filtered_genes


def _filter_proteins(proteins: pd.DataFrame,
                     filtered_complexes: pd.DataFrame,
                     interacting_partners: pd.DataFrame) -> (pd.DataFrame, pd.DataFrame):
    interacting_proteins = pd.concat([filtered_complexes[f'uniprot_{i}'] for i in range(1, 5)]).drop_duplicates()

    filtered_proteins = proteins[
        proteins['uniprot'].isin(interacting_partners) | proteins['uniprot'].isin(interacting_proteins)]

    return filtered_proteins, interacting_proteins


def _filter_complexes(complexes: pd.DataFrame, interacting_partners: pd.DataFrame) -> pd.DataFrame:
    filtered_complexes = complexes[complexes['complex_name'].isin(interacting_partners)]

    return filtered_complexes


def _merge_proteins(curated,
                    additional: pd.DataFrame,
                    log_file: str) -> pd.DataFrame:
    additional = additional.copy()

    defaults = {
        'transmembrane': False,
        'peripheral': False,
        'secreted': False,
        'secreted_desc': pd.np.nan,
        'secreted_highlight': False,
        'receptor': False,
        'receptor_desc': pd.np.nan,
        'integrin': False,
        'other': False,
        'other_desc': pd.np.nan,
        'tags': 'To_add',
        'tags_reason': pd.np.nan,
        'tags_description': pd.np.nan,
        'transporter': False
    }

    default_types = {
        'uniprot': str,
        'protein_name': str,
        'transmembrane': bool,
        'peripheral': bool,
        'secreted': bool,
        'secreted_desc': str,
        'secreted_highlight': bool,
        'receptor': bool,
        'receptor_desc': str,
        'integrin': bool,
        'other': bool,
        'other_desc': str,
        'tags': str,
        'tags_reason': str,
        'tags_description': str,
    }

    used_cols = ['uniprot', 'protein_name'] + list(defaults.keys())

    # homogeneized column names
    additional.rename(index=str, columns={'Entry': 'uniprot', 'Entry name': 'protein_name'}, inplace=True)

    # Here we set defaults for uniprot & curated data
    _set_defaults(curated, defaults)
    _set_defaults(additional, defaults)

    # we will only use these columns
    additional: pd.DataFrame = additional[used_cols]
    curated: pd.DataFrame = curated[used_cols]

    # Type casting to ensure they are equal
    additional = additional.astype(default_types)
    curated = curated.astype(default_types)

    additional_is_in_curated = additional['uniprot'].isin(curated['uniprot'])
    curated_is_in_additional = curated['uniprot'].isin(additional['uniprot'])

    common_additional: pd.DataFrame = additional.reindex(used_cols, axis=1)[additional_is_in_curated]
    common_curated: pd.DataFrame = curated.reindex(used_cols, axis=1)[curated_is_in_additional]

    distinct_additional = additional[~additional_is_in_curated]
    distinct_curated = curated[~curated_is_in_additional]

    result: pd.DataFrame = pd.concat([common_curated, distinct_additional, distinct_curated],
                                     ignore_index=True).sort_values(by='uniprot')

    if not common_curated.equals(common_additional):
        app_logger.warning('There are differences between merged files: logged to {}'.format(log_file))

        common_curated['file'] = 'curated'
        common_additional['file'] = 'additional'

        log = common_curated.append(common_additional).sort_values(by=used_cols)
        log.to_csv(log_file, index=False, sep='\t')

    return result


def _merge_complex(curated, additional, log_file):
    additional = additional.copy()

    defaults = {
        'uniprot_3': pd.np.nan,
        'uniprot_4': pd.np.nan,
        'receptor': False,
        'integrin': False,
        'other': False,
        'other_desc': pd.np.nan,
        'peripheral': False,
        'receptor_desc': pd.np.nan,
        'secreted_desc': pd.np.nan,
        'secreted_highlight': False,
        'secreted': False,
        'transmembrane': False,
        'pdb_structure': False,
        'pdb_id': pd.np.nan,
        'stoichiometry': pd.np.nan,
        'comments_complex': pd.np.nan
    }

    default_types = {
        'complex_name': str,
        'uniprot_1': str,
        'uniprot_2': str,
        'uniprot_3': str,
        'uniprot_4': str,
        'transmembrane': bool,
        'peripheral': bool,
        'secreted': bool,
        'secreted_desc': str,
        'secreted_highlight': bool,
        'receptor': bool,
        'receptor_desc': str,
        'integrin': bool,
        'other': bool,
        'other_desc': str,
        'pdb_id': str,
        'pdb_structure': str,
        'stoichiometry': str,
        'comments_complex': str,
    }

    required_columns = ['complex_name', 'uniprot_1', 'uniprot_2']

    if not set(required_columns).issubset(additional):
        raise MissingRequiredColumns(list(set(required_columns).difference(additional)))

    used_cols = required_columns + list(defaults.keys())

    # Here we set defaults for curated & user data
    _set_defaults(curated, defaults)
    _set_defaults(additional, defaults)

    # Type casting to ensure they are equal
    curated = curated.astype(default_types)
    additional = additional.astype(default_types)

    # we will only use these columns
    additional: pd.DataFrame = additional[used_cols]
    curated: pd.DataFrame = curated[used_cols]

    join_key = 'complex_name'
    additional_is_in_curated = additional[join_key].isin(curated[join_key])
    curated_is_in_additional = curated[join_key].isin(additional[join_key])

    common_additional: pd.DataFrame = additional.reindex(used_cols, axis=1)[additional_is_in_curated]
    common_curated: pd.DataFrame = curated.reindex(used_cols, axis=1)[curated_is_in_additional]

    distinct_additional = additional[~additional_is_in_curated]
    distinct_curated = curated[~curated_is_in_additional]

    result: pd.DataFrame = pd.concat([common_curated, distinct_additional, distinct_curated],
                                     ignore_index=True).sort_values(by=join_key)

    if not common_curated.equals(common_additional):
        app_logger.warning('There are differences between merged files: logged to {}'.format(log_file))

        common_curated['file'] = 'curated'
        common_additional['file'] = 'additional'

        log = common_curated.append(common_additional).sort_values(by=used_cols)
        log.to_csv(log_file, index=False, sep='\t')

    return result


def _merge_df(curated_df, additional_df, log_file, used_cols: List, join_key):
    additional_df = additional_df.copy()

    # we will only use these columns
    additional_df: pd.DataFrame = additional_df[used_cols]
    curated_df: pd.DataFrame = curated_df[used_cols]

    # type casting to ensure they are equal
    for column in additional_df:
        if additional_df[column].dtype == curated_df[column].dtype:
            continue

        print(f'converting `{column}` type from `{additional_df[column].dtype}` to `{curated_df[column].dtype}`')
        additional_df[column] = additional_df[column].astype(curated_df[column].dtype)

    additional_is_in_curated = additional_df[join_key].isin(curated_df[join_key])
    curated_is_in_additional = curated_df[join_key].isin(additional_df[join_key])

    common_additional: pd.DataFrame = additional_df.reindex(used_cols, axis=1)[additional_is_in_curated]
    common_curated: pd.DataFrame = curated_df.reindex(used_cols, axis=1)[curated_is_in_additional]

    distinct_additional = additional_df[~additional_is_in_curated]
    distinct_curated = curated_df[~curated_is_in_additional]

    result: pd.DataFrame = pd.concat([common_curated, distinct_additional, distinct_curated],
                                     ignore_index=True).sort_values(by=join_key)

    if not common_curated.equals(common_additional):
        app_logger.warning('There are differences between merged files: logged to {}'.format(log_file))

        common_curated['file'] = 'curated'
        common_additional['file'] = 'additional'

        log = common_curated.append(common_additional).sort_values(by=used_cols)
        log.to_csv(log_file, index=False, sep='\t')

    return result


def _set_defaults(df, defaults):
    for column_name, default_value in defaults.items():
        if column_name not in df:
            print('missing column in dataframe: {}, set to default {}'.format(column_name, default_value))
            df[column_name] = default_value
            continue

        df[column_name].replace({pd.np.nan: default_value}, inplace=True)


def _set_paths(output_path, subfolder):
    if not output_path:
        output_path = output_dir

    if subfolder:
        output_path = os.path.realpath(os.path.expanduser('{}/{}'.format(output_path, subfolder)))

    os.makedirs(output_path, exist_ok=True)

    if _path_is_not_empty(output_path):
        app_logger.warning(
            'Output directory ({}) exist and is not empty. Result can overwrite old results'.format(output_path))

    return output_path


def _path_is_not_empty(path):
    return bool([f for f in os.listdir(path) if not f.startswith('.')])
